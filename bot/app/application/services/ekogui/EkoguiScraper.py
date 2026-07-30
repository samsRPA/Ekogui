import re
import json
import time
import asyncio
import logging
import urllib.parse
from pathlib import Path
from typing import Optional

from app.application.headers.EkoguiHeaders import EkoguiHeaders
from app.domain.interfaces.IContextClient import IContextClient
from app.domain.interfaces.IEkoguiScraper import IEkoguiScraper

CLIENT_ID = "Ofli249wJGRCnTf9bF1x7t979uMa"

# El gateway Zuul de Ekogui a veces corta la peticion con un 500 cuando el
# backend/SGD esta lento o caido, y devuelve un cuerpo JSON de error en vez
# de la URL esperada. Es transitorio: reintentar con backoff normalmente
# resuelve. Si se propagara tal cual, ese JSON terminaria publicado como
# 'urlAuto' en la cola de autos.
_ZUUL_ERROR_RE = re.compile(r'"exception"\s*:\s*"com\.netflix\.zuul\.exception\.ZuulException"')


class EkoguiScraper(IEkoguiScraper):
    """Scraper de Ekogui (consumidor): abre UNA sesion por mensaje (login +
    SSO al modulo judicial + seleccion de la entidad del lote) y recorre
    todos los procesos de ese lote en la misma sesion, extrayendo
    actuaciones (evolucion procesal) y documentos de soporte.

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
        self.logger = logging.getLogger(__name__)

    def _cacheBuster(self) -> str:
        return str(int(time.time() * 1000))

    # ------------------------------------------------------------------
    # Login principal (/ekogui).
    # ------------------------------------------------------------------

    async def _login(self, client: IContextClient) -> bool:
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
        return loggedIn

    # ------------------------------------------------------------------
    # SSO al modulo /ekoguims + seleccion de entidad (privados).
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
        """Intenta el mismo handshake SSO de _login() pero apuntando a otro
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

    async def _seleccionarEntidad(self, client: IContextClient, moduleBaseUrl: str, entidadId: int,
                                   bearerToken: str) -> str:
        """POST /ekoguims/api/seleccionar-entidad/{entidadId} -> retorna un
        nuevo JWT ('id_token') con los permisos/perfiles de esa entidad, que
        hay que usar como Authorization: Bearer en todas las llamadas
        siguientes de ese modulo."""
        url = f"{moduleBaseUrl}/api/seleccionar-entidad/{entidadId}?cacheBuster={self._cacheBuster()}"
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
        return data["id_token"]

    # ------------------------------------------------------------------
    # Orquestador publico: login + SSO + seleccion de entidad, todo en uno.
    # ------------------------------------------------------------------

    async def iniciarSesionEntidad(self, client: IContextClient, entidadId: int) -> str:
        loggedIn = await self._login(client)
        if not loggedIn:
            raise RuntimeError("No se pudo iniciar sesion en Ekogui")

        socialAuthToken = await self._signInModule(client, self.msBaseUrl)
        return await self._seleccionarEntidad(client, self.msBaseUrl, entidadId, socialAuthToken)

    # ------------------------------------------------------------------
    # Actuaciones y documentos del proceso (modulo /ekoguims judicial).
    # ------------------------------------------------------------------

    async def listarActuacionesProceso(self, client: IContextClient, idToken: str,
                                        procesoEntidadId: int) -> list[dict]:
        """GET .../ekoguimsjudiciales/api/evolucionProcesal/procesoEntidad/{procesoEntidadId}?size=1000
        -> evolucion procesal completa (todas las actuaciones) del proceso."""
        url = (
            f"{self.msBaseUrl}/ekoguimsjudiciales/api/evolucionProcesal/procesoEntidad/{procesoEntidadId}"
            f"?cacheBuster={self._cacheBuster()}&size=1000"
        )
        headers = {
            **self.headers.XHR_HEADERS,
            "Authorization": f"Bearer {idToken}",
            "X-Xsrf-Token": self._msXsrf,
            "Referer": f"{self.msBaseUrl}/",
        }
        resp = await client.get(url, headers=headers)
        self._refreshMsXsrf(resp)
        data = await resp.json(content_type=None)
        actuaciones = data.get("lstActuaciones", [])
        return actuaciones

    async def listarDocumentosProceso(self, client: IContextClient, idToken: str,
                                       procesoId: int) -> list[dict]:
        """GET .../ekoguimsjudiciales/api/documento-soporte/obtenerDocumentosSoporteEntidadPorProceso/{procesoId}
        -> lista de documentos de soporte del proceso (cada uno con
        'archivoId', 'archivoIdSgd', 'tipoAnexoDescripcion', 'nombre',
        'extension')."""
        url = (
            f"{self.msBaseUrl}/ekoguimsjudiciales/api/documento-soporte/obtenerDocumentosSoporteEntidadPorProceso/{procesoId}"
            f"?cacheBuster={self._cacheBuster()}&method=obtenerDocumentosSoporteEntidadesProcesoId"
        )
        headers = {
            **self.headers.XHR_HEADERS,
            "Authorization": f"Bearer {idToken}",
            "X-Xsrf-Token": self._msXsrf,
            "Referer": f"{self.msBaseUrl}/",
        }
        resp = await client.get(url, headers=headers)
        self._refreshMsXsrf(resp)
        documentos = await resp.json(content_type=None)
        return documentos

    async def obtenerUrlDocumento(self, client: IContextClient, idToken: str,
                                   procesoId: int, archivoId: int,
                                   maxRetries: int = 3, backoffSeconds: float = 2.0) -> str:
        """GET .../ekoguimstransversales/api/documento-soporte/obtenerURLDocumentoSoporte/{procesoId}/{archivoId}
        -> URL de texto plano (https://sgdea.../mercurio/consulta/imagen?g=<hash>)
        que hay que visitar para que el SGD genere el archivo temporal
        descargable. Si el gateway Zuul devuelve un 500 SHORTCIRCUIT/GENERAL
        (backend/SGD lento o caido), reintenta con backoff antes de
        rendirse. Nunca retorna un cuerpo que no sea una URL http(s) real
        -> evita publicar basura como 'urlAuto' en la cola de autos."""
        url = (
            f"{self.msBaseUrl}/ekoguimstransversales/api/documento-soporte/obtenerURLDocumentoSoporte/{procesoId}/{archivoId}"
            f"?cacheBuster={self._cacheBuster()}&method=obtenerURLDocumentoSoporte"
        )
        headers = {
            **self.headers.XHR_HEADERS,
            "Authorization": f"Bearer {idToken}",
            "X-Xsrf-Token": self._msXsrf,
            "Referer": f"{self.msBaseUrl}/",
        }

        for attempt in range(1, maxRetries + 1):
            resp = await client.get(url, headers=headers)
            self._refreshMsXsrf(resp)
            body = (await resp.text()).strip()

            if "%3A" in body or "%2F" in body:
                body = urllib.parse.unquote(body)

            if resp.status == 200 and body.lower().startswith(("http://", "https://")):
                return body

            if resp.status >= 500 and _ZUUL_ERROR_RE.search(body) and attempt < maxRetries:
                wait = backoffSeconds * attempt
                self.logger.warning(
                    f"🟡 Zuul devolvio error transitorio (status={resp.status}) al resolver URL de "
                    f"procesoId={procesoId} archivoId={archivoId}; reintentando en {wait}s "
                    f"(intento {attempt}/{maxRetries})"
                )
                await asyncio.sleep(wait)
                continue

            raise RuntimeError(
                f"Respuesta invalida al resolver URL de documento (status={resp.status} "
                f"procesoId={procesoId} archivoId={archivoId}): {body[:300]!r}"
            )

        raise RuntimeError(
            f"No se pudo resolver URL de documento tras {maxRetries} intentos "
            f"(procesoId={procesoId} archivoId={archivoId})"
        )
