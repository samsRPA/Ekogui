import re
import json
import time
import logging
import urllib.parse
from typing import Optional

from app.application.headers.EkoguiHeaders import EkoguiHeaders
from app.domain.interfaces.IContextClient import IContextClient
from app.domain.interfaces.IEkoguiScraper import IEkoguiScraper

CLIENT_ID = "Ofli249wJGRCnTf9bF1x7t979uMa"

# Tamano fijo de pagina al listar procesos. Entidades con muchos procesos
# (ej. ACOPENSIONES) hacen que el backend de Ekogui tarde demasiado en
# construir una pagina con size=totalElements y el cliente termina en
# TimeoutError; pedir en bloques fijos evita ese problema.
LISTING_PAGE_SIZE = 10000


class EkoguiScraper(IEkoguiScraper):
    """Scraper de Ekogui (etapa de listado): login completo (SP Angular ->
    WSO2 IS -> vuelta al SP) y listado paginado de procesos judiciales por
    entidad. La descarga de documentos por proceso vive en el consumidor,
    este productor solo necesita encontrar los radicados a publicar.

    Flujo de login confirmado con traza real de Burp Suite:
        1. GET  services.../ekogui/                         -> Set-Cookie XSRF-TOKEN
        2. POST services.../ekogui/signin/ekogui             -> 302 (sigue solo con redirects)
           (redirige a auth.../oauth2/authorize -> auth.../authenticationendpoint/login.do)
        3. POST auth.../commonauth (usuario/password)        -> 302 (sigue solo con redirects)
           (redirige a auth.../oauth2/authorize -> services.../ekogui/signin/ekogui?code=...
            -> Set-Cookie social-authentication -> services.../ekogui/ ya logueado)
    """

    def __init__(self, documentType: str, documentNumber: str, password: str,
                 authBaseUrl: str = "https://auth.defensajuridica.gov.co:9443",
                 appOrigin: str = "https://services.defensajuridica.gov.co"):
        self.documentType = documentType
        self.documentNumber = documentNumber
        self.password = password
        self.authBaseUrl = authBaseUrl
        self.appOrigin = appOrigin
        self.appBaseUrl = f"{appOrigin}/ekogui"
        self.msBaseUrl = f"{appOrigin}/ekoguims"
        self.headers = EkoguiHeaders
        self._csrf: Optional[str] = None
        self._sessionDataKey: Optional[str] = None
        self._msXsrf: Optional[str] = None
        self._msSocialAuthToken: Optional[str] = None
        self._entityTokens: dict[int, str] = {}
        self.logger = logging.getLogger(__name__)

    def _cacheBuster(self) -> str:
        return str(int(time.time() * 1000))

    # ------------------------------------------------------------------
    # Login principal (/ekogui).
    # ------------------------------------------------------------------

    async def login(self, client: IContextClient) -> bool:
        """Ejecuta el flujo completo de autenticacion y retorna True si al
        final quedamos con la sesion logueada (home de Ekogui, no el login)."""
        self.logger.info(f"🔐 Iniciando sesion para cedula {self.documentType}|{self.documentNumber}")
        xsrfToken = await self._openHomePage(client)
        sessionDataKey = await self._startSignIn(client, xsrfToken)
        return await self._submitCredentials(client, sessionDataKey)

    async def _openHomePage(self, client: IContextClient) -> str:
        """Paso 1: GET /ekogui/. Crea el XSRF-TOKEN (cookie de la app
        Angular/Spring, path=/ekogui) que hay que reenviar como '_csrf' en el
        POST de signin."""
        url = f"{self.appBaseUrl}/"
        resp = await client.get(url, headers=self.headers.NAV_HEADERS)
        await resp.read()

        xsrfCookie = resp.cookies.get("XSRF-TOKEN")
        if xsrfCookie is None:
            raise RuntimeError("No se recibio la cookie XSRF-TOKEN en GET /ekogui/")

        token = xsrfCookie.value
        #self.logger.info(f"[Paso 1] GET /ekogui/ -> {resp.status} (XSRF-TOKEN=ok)")
        return token

    async def _startSignIn(self, client: IContextClient, xsrfToken: str) -> str:
        """Paso 2: POST /ekogui/signin/ekogui con scope='' y _csrf=XSRF-TOKEN.
        El SP responde 302 hacia auth.../oauth2/authorize, que a su vez
        redirige a auth.../authenticationendpoint/login.do?...&sessionDataKey=...
        El cliente HTTP sigue ambos redirects solo (GET automatico), y
        terminamos con la URL final del login.do de donde sacamos el
        sessionDataKey fresco."""
        url = f"{self.appBaseUrl}/signin/ekogui"
        data = {"scope": "", "_csrf": xsrfToken}
        headers = {
            **self.headers.FORM_POST_HEADERS,
            "Origin": self.appOrigin,
            "Referer": f"{self.appBaseUrl}/",
        }
        resp = await client.post(url, data=data, headers=headers)
        html = await resp.text()

        finalUrl = str(resp.url)
        sessionDataKeyMatch = re.search(r"sessionDataKey=([0-9a-f-]+)", finalUrl) or \
            re.search(r'name="sessionDataKey"\s+value=\'([^\']+)\'', html)
        if not sessionDataKeyMatch:
            raise RuntimeError(f"No se pudo obtener sessionDataKey tras signin/ekogui (url final: {finalUrl})")
        self._sessionDataKey = sessionDataKeyMatch.group(1)

        csrfMatch = re.search(r"_csrf=([0-9a-f-]+)", finalUrl)
        if csrfMatch:
            self._csrf = csrfMatch.group(1)

       # self.logger.info(f"[Paso 2] POST signin/ekogui -> {resp.status} (final={finalUrl}) sessionDataKey=ok")
        return self._sessionDataKey

    async def _submitCredentialsTo(self, client: IContextClient, loginDoUrl: str, sessionDataKey: str):
        """POST auth.../commonauth con usuario/clave, usando el
        sessionDataKey y la URL de login.do (como Referer/Origin de
        referencia) de la peticion de login.do que corresponda. Reutilizable
        tanto para el login principal (/ekogui) como para el SSO de otros
        modulos (/ekoguims) cuando la reutilizacion silenciosa de sesion
        falla y WSO2 vuelve a pedir credenciales."""
        data = {
            "tipoDoc": self.documentType,
            "username": f"{self.documentType}|{self.documentNumber}",
            "document-number": self.documentNumber,
            "password": self.password,
            "terminos_condiciones": "on",
            "sessionDataKey": sessionDataKey,
        }
        headers = {
            **self.headers.FORM_POST_HEADERS,
            "Origin": self.authBaseUrl,
            "Referer": loginDoUrl,
        }
        resp = await client.post(f"{self.authBaseUrl}/commonauth", data=data, headers=headers)
        html = await resp.text()
        return resp, html

    async def _submitCredentials(self, client: IContextClient, sessionDataKey: str) -> bool:
        """Paso 3 del login principal (/ekogui): POST auth.../commonauth con
        usuario/clave. En exito el IS redirige (302) -> oauth2/authorize?
        sessionDataKey=... -> vuelve al SP con ?code=...&state=... -> el SP
        setea social-authentication y redirige a /ekogui/ ya logueado."""
        loginDoUrl = (
            f"{self.authBaseUrl}/authenticationendpoint/login.do?_csrf={self._csrf}"
            f"&client_id={CLIENT_ID}&commonAuthCallerPath=%2Foauth2%2Fauthorize"
            f"&forceAuth=false&passiveAuth=false&redirect_uri={self.appBaseUrl}/signin/ekogui"
            f"&response_type=code&scope=&tenantDomain=carbon.super&sessionDataKey={sessionDataKey}"
            f"&relyingParty={CLIENT_ID}&type=oauth2&sp=ekogui2.prod&isSaaSApp=false"
            f"&authenticators=BasicAuthenticator:LOCAL"
        )
        resp, html = await self._submitCredentialsTo(client, loginDoUrl, sessionDataKey)

        loggedIn = resp.status == 200 and "ng-app=ekoguiApp" in html and 'id="loginForm"' not in html
        #self.logger.info(f"[Paso 3] POST commonauth -> {resp.status} (final={resp.url}) login={'OK' if loggedIn else 'FALLIDO'}")
        return loggedIn

    # ------------------------------------------------------------------
    # Datos de la persona / entidades disponibles (modulo /ekogui).
    # ------------------------------------------------------------------

    async def getUserPersonId(self, client: IContextClient) -> int:
        """GET /ekogui/api/buscarPersonaUsuario/{tipoDoc}|{documento} ->
        retorna el 'id' de persona (personId), usado luego para consultar
        las entidades a las que esa persona tiene acceso."""
        identification = f"{self.documentType.lower()}%7C{self.documentNumber}"
        url = f"{self.appBaseUrl}/api/buscarPersonaUsuario/{identification}?cacheBuster={self._cacheBuster()}"
        headers = {
            **self.headers.XHR_HEADERS,
            "X-Xsrf-Token": self._csrf,
            "Referer": f"{self.appBaseUrl}/",
        }
        resp = await client.get(url, headers=headers)
        data = await resp.json(content_type=None)
        #self.logger.info(f"[buscarPersonaUsuario] -> {resp.status} personaId={data.get('id')}")
        return data["id"]

    async def getPersonEntities(self, client: IContextClient, personId: int) -> list[dict]:
        """GET /ekogui/api/obtenerEntidadesPersona/{personId} -> lista de
        entidades (cada una con 'id' y 'nombre') a las que el usuario tiene
        acceso para gestionar procesos judiciales."""
        url = f"{self.appBaseUrl}/api/obtenerEntidadesPersona/{personId}?cacheBuster={self._cacheBuster()}"
        headers = {
            **self.headers.XHR_HEADERS,
            "X-Xsrf-Token": self._csrf,
            "Referer": f"{self.appBaseUrl}/",
        }
        resp = await client.get(url, headers=headers)
        entities = await resp.json(content_type=None)
        #self.logger.info(f"[getPersonEntities] -> {resp.status} ({len(entities)} entidad(es))")
        return entities

    # ------------------------------------------------------------------
    # Orquestador publico: SSO + seleccion de entidad (una sola vez por
    # entityId, cacheado) + listado paginado. El llamador no necesita saber
    # nada de moduleBaseUrl, tokens ni XSRF-TOKEN rotativo.
    # ------------------------------------------------------------------

    async def listEntityProcesses(self, client: IContextClient, entityId: int,
                                  entityName: str,
                                  state: str = "PROCESO_ENTIDAD_ACTIVO") -> list[dict]:
        """Trae TODOS los procesos de la entidad, sin que el llamador tenga
        que paginar: se pide 'totalElements' con una pagina minima y luego
        se pide esa misma cantidad como 'size'. Ekogui puede limitar el
        tamano real de cada respuesta (el 'totalPages' que devuelve refleja
        ese tope real, sea cual sea), asi que se sigue pidiendo pagina tras
        pagina -segun lo que el propio servidor reporte, sin ningun tope fijo
        en el codigo- hasta juntar el total."""
        if self._msSocialAuthToken is None:
            self._msSocialAuthToken = await self._signInModule(client, self.msBaseUrl)

        idToken = self._entityTokens.get(entityId)
        if idToken is None:
            idToken = await self._selectEntity(client, self.msBaseUrl, entityId, entityName, self._msSocialAuthToken)
            self._entityTokens[entityId] = idToken

        self.logger.info(f"⏏️ Extrayendo procesos - entidadId={entityId} ({entityName}) estado={state}")

        count = await self._listProcesses(client, self.msBaseUrl, idToken, entityId, state, page=0, size=1)
        totalElements = count.get("totalElements", 0)
        if not totalElements:
            self.logger.warning(f"🟡 entidadId={entityId} ({entityName}) sin procesos en estado={state}")
            return []

        pageData = await self._listProcesses(client, self.msBaseUrl, idToken, entityId, state, page=0, size=LISTING_PAGE_SIZE)
        newItems = pageData.get("content", [])
        processes = list(newItems)
        totalPages = pageData.get("totalPages", 1)
        self.logger.info(
            f"📥 entidadId={entityId} ({entityName}) pagina=0 extrajo={len(newItems)} van={len(processes)}/{totalElements}"
        )

        page = 1
        while len(processes) < totalElements and page < totalPages:
            pageData = await self._listProcesses(client, self.msBaseUrl, idToken, entityId, state, page=page, size=LISTING_PAGE_SIZE)
            newItems = pageData.get("content", [])
            processes.extend(newItems)
            self.logger.info(
                f"📥 entidadId={entityId} ({entityName}) pagina={page} extrajo={len(newItems)} van={len(processes)}/{totalElements}"
            )
            page += 1

        return processes

    async def searchProcessByCaseNumber(self, client: IContextClient, entityId: int,
                                        entityName: str, caseNumber: str,
                                        state: str = "PROCESO_ENTIDAD_ACTIVO") -> Optional[dict]:
        """Busca UN proceso puntual por su numeroProceso (radicado) dentro de
        la entidad, usando el mismo campo 'filtroBuscar' que usa el buscador
        de la UI de Ekogui. Retorna el proceso si lo encuentra, o None."""
        if self._msSocialAuthToken is None:
            self._msSocialAuthToken = await self._signInModule(client, self.msBaseUrl)

        idToken = self._entityTokens.get(entityId)
        if idToken is None:
            idToken = await self._selectEntity(client, self.msBaseUrl, entityId, entityName, self._msSocialAuthToken)
            self._entityTokens[entityId] = idToken

        pageData = await self._listProcesses(client, self.msBaseUrl, idToken, entityId, state,
                                             page=0, size=1, searchFilter=caseNumber)
        content = pageData.get("content", [])
        return content[0] if content else None

    async def searchProcessesByCaseNumbers(self, client: IContextClient, entityId: int,
                                           entityName: str, caseNumbers: set[str],
                                           state: str = "PROCESO_ENTIDAD_ACTIVO") -> list[dict]:
        """Bulk lookup of case numbers WITHOUT one request per case number:
        walks the same paginated listing used by listEntityProcesses
        (LISTING_PAGE_SIZE chunks) and filters locally by numeroProceso. Only
        matching processes are kept in memory (not the whole entity), and
        paging stops as soon as every requested case number has shown up."""
        if self._msSocialAuthToken is None:
            self._msSocialAuthToken = await self._signInModule(client, self.msBaseUrl)

        idToken = self._entityTokens.get(entityId)
        if idToken is None:
            idToken = await self._selectEntity(client, self.msBaseUrl, entityId, entityName, self._msSocialAuthToken)
            self._entityTokens[entityId] = idToken

        self.logger.info(
            f"⏏️ Searching {len(caseNumbers)} case numbers in listing - entityId={entityId} ({entityName}) state={state}"
        )

        count = await self._listProcesses(client, self.msBaseUrl, idToken, entityId, state, page=0, size=1)
        totalElements = count.get("totalElements", 0)
        if not totalElements:
            self.logger.warning(f"🟡 entityId={entityId} ({entityName}) has no processes in state={state}")
            return []

        pending = set(caseNumbers)
        found: list[dict] = []
        seenIds: set = set()

        def collectMatches(content: list[dict]) -> None:
            for process in content:
                caseNumber = str(process.get("numeroProceso") or "").strip()
                if caseNumber not in caseNumbers or process.get("id") in seenIds:
                    continue
                seenIds.add(process.get("id"))
                found.append(process)
                pending.discard(caseNumber)

        pageData = await self._listProcesses(client, self.msBaseUrl, idToken, entityId, state, page=0, size=LISTING_PAGE_SIZE)
        content = pageData.get("content", [])
        collectMatches(content)
        scanned = len(content)
        totalPages = pageData.get("totalPages", 1)
        self.logger.info(
            f"📥 entityId={entityId} ({entityName}) page=0 scanned={scanned}/{totalElements} "
            f"found={len(found)} pending={len(pending)}"
        )

        page = 1
        while pending and scanned < totalElements and page < totalPages:
            pageData = await self._listProcesses(client, self.msBaseUrl, idToken, entityId, state, page=page, size=LISTING_PAGE_SIZE)
            content = pageData.get("content", [])
            collectMatches(content)
            scanned += len(content)
            self.logger.info(
                f"📥 entityId={entityId} ({entityName}) page={page} scanned={scanned}/{totalElements} "
                f"found={len(found)} pending={len(pending)}"
            )
            page += 1

        if not pending:
            self.logger.info(f"🟢 entityId={entityId} ({entityName}) all case numbers found; stopped paging at page={page - 1}")

        return found

    # ------------------------------------------------------------------
    # SSO al modulo /ekoguims y listado paginado de procesos (privados).
    # ------------------------------------------------------------------

    def _refreshMsXsrf(self, resp) -> None:
        """El modulo /ekoguims rota el XSRF-TOKEN en CADA respuesta (borra el
        viejo y setea uno nuevo via Set-Cookie). Si no se usa el valor mas
        reciente en la siguiente peticion, el CSRF check del backend la
        rechaza."""
        cookie = resp.cookies.get("XSRF-TOKEN")
        if cookie:
            self._msXsrf = cookie.value

    async def _signInModule(self, client: IContextClient, moduleBaseUrl: str) -> str:
        """Intenta el mismo handshake SSO de login() pero apuntando a otro
        modulo (/ekoguims), esperando que el IS reconozca la sesion ya
        autenticada (cookie commonAuthId) y redirija directo sin pedir
        credenciales de nuevo.

        En la practica esto no siempre ocurre (el IS puede volver a mostrar
        el formulario de login.do aunque exista una sesion valida), asi que
        si se detecta el formulario de login en la respuesta, se hace un
        fallback: se resuelve ese login.do como un login normal, reenviando
        usuario/clave via _submitCredentialsTo con el sessionDataKey de ESA
        cadena de redirects.

        Guarda el XSRF-TOKEN del modulo y retorna el JWT
        'social-authentication' (el que hay que mandar como Authorization:
        Bearer en seleccionar-entidad)."""
        resp = await client.get(f"{moduleBaseUrl}/", headers=self.headers.NAV_HEADERS)
        await resp.read()
        xsrfCookie = resp.cookies.get("XSRF-TOKEN")
        if xsrfCookie is None:
            raise RuntimeError(f"No se recibio XSRF-TOKEN en GET {moduleBaseUrl}/")
        xsrfToken = xsrfCookie.value

        data = {"scope": "", "_csrf": xsrfToken}
        headers = {
            **self.headers.FORM_POST_HEADERS,
            "Origin": self.appOrigin,
            "Referer": f"{moduleBaseUrl}/",
        }
        resp = await client.post(f"{moduleBaseUrl}/signin/ekogui", data=data, headers=headers)
        html = await resp.text()

        if 'id="loginForm"' in html:
            loginDoUrl = str(resp.url)
            sessionDataKeyMatch = re.search(r"sessionDataKey=([0-9a-f-]+)", loginDoUrl)
            if not sessionDataKeyMatch:
                raise RuntimeError(f"SSO silencioso fallo en {moduleBaseUrl} y no se pudo extraer sessionDataKey para reintentar con credenciales")
            resp, html = await self._submitCredentialsTo(client, loginDoUrl, sessionDataKeyMatch.group(1))

        # El Set-Cookie de 'social-authentication' puede llegar en cualquier
        # hop intermedio del redirect (no necesariamente en la respuesta
        # final), asi que se busca en todo el historial seguido por aiohttp.
        socialAuthToken = None
        for hop in list(resp.history) + [resp]:
            cookie = hop.cookies.get("social-authentication")
            if cookie:
                socialAuthToken = cookie.value
            cookie = hop.cookies.get("XSRF-TOKEN")
            if cookie:
                xsrfToken = cookie.value

        self._msXsrf = xsrfToken
        loggedIn = resp.status == 200 and 'id="loginForm"' not in html
        if not loggedIn:
            raise RuntimeError(f"No se pudo iniciar sesion en {moduleBaseUrl} (status={resp.status})")
        if socialAuthToken is None:
            raise RuntimeError(f"No se encontro la cookie social-authentication tras el login a {moduleBaseUrl}")

        self.logger.info(f"🟢 Sesion iniciada en {moduleBaseUrl}")
        return socialAuthToken

    async def _selectEntity(self, client: IContextClient, moduleBaseUrl: str, entityId: int,
                            entityName: str, bearerToken: str) -> str:
        """POST /ekoguims/api/seleccionar-entidad/{entityId} -> retorna un
        nuevo JWT ('id_token') con los permisos/perfiles de esa entidad, que
        hay que usar como Authorization: Bearer en todas las llamadas
        siguientes de ese modulo."""
        url = f"{moduleBaseUrl}/api/seleccionar-entidad/{entityId}?cacheBuster={self._cacheBuster()}"
        headers = {
            **self.headers.XHR_HEADERS,
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {bearerToken}",
            "X-Xsrf-Token": self._msXsrf,
            "Origin": self.appOrigin,
            "Referer": f"{moduleBaseUrl}/",
        }
        resp = await client.post(url, data=json.dumps({}), headers=headers)
        self._refreshMsXsrf(resp)
        data = await resp.json(content_type=None)
        self.logger.info(f"[seleccionarEntidad] entidadId={entityId} ({entityName})")
        if resp.status != 200 or not isinstance(data, dict) or "id_token" not in data:
            raise RuntimeError(
                f"No se pudo seleccionar la entidad entidadId={entityId} ({entityName}): "
                f"status={resp.status} respuesta={data!r}"
            )
        return data["id_token"]

    async def _listProcesses(self, client: IContextClient, moduleBaseUrl: str, idToken: str,
                             entityId: int, state: str = "PROCESO_ENTIDAD_ACTIVO",
                             page: int = 0, size: int = 100,
                             searchFilter: Optional[str] = None) -> dict:
        """GET .../ekoguimsjudiciales/api/procesos/dominiodata/{filtro} ->
        pagina de procesos de la entidad (dict con 'content', 'totalPages',
        'last', etc). El filtro va como JSON URL-encoded DOS veces (asi
        viaja en la traza real). 'searchFilter' viaja como 'filtroBuscar', el
        mismo campo que usa el buscador de la UI de Ekogui: si se manda el
        numeroProceso exacto, Ekogui devuelve solo ese proceso."""
        filterPayload = {
            "orden": None,
            "filtroBuscar": searchFilter,
            "estado": state,
            "entidadId": str(entityId),
            "modulo": "",
            "depEspecialId": None,
            "depEspecialList": [],
            "llave": state,
            "tieneRepresentacionJudicial": None,
        }
        filterJson = json.dumps(filterPayload, separators=(",", ":"))
        doubleEncodedFilter = urllib.parse.quote(urllib.parse.quote(filterJson, safe=""), safe="")

        url = (
            f"{moduleBaseUrl}/ekoguimsjudiciales/api/procesos/dominiodata/{doubleEncodedFilter}"
            f"?cacheBuster={self._cacheBuster()}&page={page}&size={size}"
        )
        headers = {
            **self.headers.XHR_HEADERS,
            "Authorization": f"Bearer {idToken}",
            "X-Xsrf-Token": self._msXsrf,
            "Referer": f"{moduleBaseUrl}/",
        }
        resp = await client.get(url, headers=headers)
        self._refreshMsXsrf(resp)
        data = await resp.json(content_type=None)
        return data
