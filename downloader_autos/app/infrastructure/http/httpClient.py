import re
import uuid
import asyncio
import logging
from typing import AsyncIterator, List, Optional
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientSession, TCPConnector, ClientTimeout

from app.domain.interfaces.IHttpClient import IHttpClient
from app.domain.interfaces.IContextClient import IContextClient
from app.domain.dto.FetchedDocument import FetchedDocument
from app.domain.dto.ContentTypeSniffer import ContentTypeSniffer

class AioHttpClient(IHttpClient):
    def __init__(self, proxies: List[Optional[str]] = None, maxConnections: int = 20, timeoutSeconds: int = 120):
        self._proxies = proxies or []
        self._index: int = 0
        self._sessionId: str = uuid.uuid4().hex
        self.session: ClientSession = None
        self.maxConnections = maxConnections
        self.timeoutSeconds = timeoutSeconds
        self.logger = logging.getLogger(__name__)

    def _currentProxy(self) -> Optional[str]:
        if not self._proxies:
            return None
        return self._proxies[self._index]

    def _proxyHeaders(self, sessionId: str) -> Optional[dict]:
        if not self._currentProxy():
            return None
        return {"X-SESSION-ID": sessionId}

    def _advance(self, failed: bool) -> None:
        if not self._proxies or not failed:
            return
        label = self._proxies[self._index] or "sin proxy"
        self.logger.warning(f"🔴 Proxy fallido ({label}), rotando al siguiente")
        self._index = (self._index + 1) % len(self._proxies)
        self._sessionId = uuid.uuid4().hex

    async def init(self):
        try:
            timeout = ClientTimeout(
                total=self.timeoutSeconds,
                connect=self.timeoutSeconds,
                sock_read=self.timeoutSeconds,
                sock_connect=self.timeoutSeconds,
            )
            self.session = ClientSession(
                connector=TCPConnector(
                    limit=self.maxConnections,
                    force_close=True,
                    enable_cleanup_closed=True,
                ),
                timeout=timeout,
                trust_env=False,
            )
            self.logger.info("🔵 Cliente http creado exitosamente.")
        except Exception as e:
            raise RuntimeError(f"Error inesperado al iniciar cliente http: {e}")

    @asynccontextmanager
    async def contextClient(self) -> AsyncIterator[IContextClient]:
        proxy = self._currentProxy()
        proxyHeaders = self._proxyHeaders(self._sessionId)
        self.logger.info(f"🌐 Sesión con proxy: {proxy or 'sin proxy'} | session: {self._sessionId}")

        timeout = ClientTimeout(
            total=self.timeoutSeconds,
            connect=self.timeoutSeconds,
            sock_read=self.timeoutSeconds,
            sock_connect=self.timeoutSeconds,
        )
        tempSession = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            },
            connector=TCPConnector(
                limit=self.maxConnections,
                force_close=True,
                enable_cleanup_closed=True,
            ),
            timeout=timeout,
            trust_env=False,
        )

        outer = self

        class TempHttp:
            def __init__(self, session: aiohttp.ClientSession):
                self.session = session

            async def get(self, url, headers=None):
                # Pass all jar cookies explicitly so cross-subdomain requests (e.g.
                # samaicore.* downloading from a session built on samai.*) still
                # carry the session cookies that aiohttp's domain filter would drop.
                max_attempts = max(1, len(outer._proxies))
                for attempt in range(max_attempts):
                    current_proxy = outer._currentProxy()
                    current_proxy_headers = outer._proxyHeaders(outer._sessionId)
                    all_cookies = {m.key: m.value for m in self.session.cookie_jar}
                    try:
                        return await asyncio.wait_for(
                            self.session.get(url, headers=headers, cookies=all_cookies or None, proxy=current_proxy, proxy_headers=current_proxy_headers),
                            timeout=outer.timeoutSeconds,
                        )
                    except (aiohttp.ClientHttpProxyError, aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                        if attempt < max_attempts - 1:
                            self.logger.warning(f"🔴 Proxy caído ({current_proxy or 'sin proxy'}), rotando y reintentando en 3s...")
                            outer._advance(failed=True)
                            await asyncio.sleep(3)
                        else:
                            raise

            async def post(self, url, data=None, json=None, headers=None):
                return await self.session.post(url, data=data, json=json, headers=headers, proxy=proxy, proxy_headers=proxyHeaders)

        sessionFailed = False
        try:
            self.logger.info("Cliente temporal creado")
            yield TempHttp(tempSession)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            sessionFailed = True
            raise
        except Exception:
            raise
        finally:
            try:
                await tempSession.close()
                self.logger.info("Cliente temporal cerrado correctamente")
            except Exception:
                self.logger.warning("🟡 Cliente temporal no cerrado")
            self._advance(failed=sessionFailed)

    def invalidateProxy(self) -> None:
        self._advance(failed=True)

    async def getHeaders(self, url: str, headers: dict = None) -> dict:
        proxy = self._currentProxy()
        proxyHeaders = self._proxyHeaders(self._sessionId)
        try:
            async with self.session.head(url, headers=headers, proxy=proxy, proxy_headers=proxyHeaders, allow_redirects=True) as resp:
                return dict(resp.headers)
        except Exception as e:
            raise RuntimeError(f"Error al obtener headers de {url}: {e}")

    async def detectMimeType(self, url: str) -> str | None:
        mimeExtMap = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
            "application/vnd.ms-excel": ".xls",
        }
        proxy = self._currentProxy()
        proxyHeaders = self._proxyHeaders(self._sessionId)
        try:
            async with self.session.head(url, proxy=proxy, proxy_headers=proxyHeaders, allow_redirects=True) as resp:
                ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                return mimeExtMap.get(ct)
        except Exception:
            return None

    def _resolvedContentType(self, response: aiohttp.ClientResponse, content: bytes, fileName: Optional[str]) -> str:
        declared = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ContentTypeSniffer.isUnreliable(declared):
            declared = ContentTypeSniffer.sniffContentType(content) or declared
        return ContentTypeSniffer.refineByExtension(declared, fileName)

    async def _fetchBinary(self, url: str, fallbackFileName: Optional[str] = None, maxRetries: int = 2) -> FetchedDocument:
        lastError = None
        for attempt in range(1, maxRetries + 1):
            proxy = self._currentProxy()
            proxyHeaders = self._proxyHeaders(uuid.uuid4().hex)
            try:
                async with self.session.get(url, proxy=proxy, proxy_headers=proxyHeaders) as response:
                    response.raise_for_status()
                    content = await response.read()
                    fileName = ContentTypeSniffer.fileNameFromDisposition(response.headers.get("Content-Disposition")) or fallbackFileName
                    contentType = self._resolvedContentType(response, content, fileName)
                    return FetchedDocument(content=content, contentType=contentType, url=str(response.url), fileName=fileName)
            except Exception as e:
                lastError = e
                if self._proxies:
                    self.logger.warning(f"🟡 Error en descarga, intento {attempt}/{maxRetries}, rotando proxy: {e}")
                    self._advance(failed=True)
                else:
                    self.logger.warning(f"🟡 Error en descarga, intento {attempt}/{maxRetries}, reintentando: {e}")

        raise RuntimeError(f"Descarga fallida tras {maxRetries} intentos - {url}: {lastError}")

    async def fetchDocument(self, imagenUrl: str) -> Optional[FetchedDocument]:
        """GET a la URL 'imagen?g=<hash>' de Ekogui. Puede devolver dos cosas:
        (a) el archivo binario final directo (PDF/imagen/word), o
        (b) una pagina HTML intermedia con un <embed src='...temporales\\<archivo>.pdf'>
            que hay que seguir para obtener el archivo real.
        Antes este metodo asumia siempre (b) y hacia await response.text(),
        lo que explota con UnicodeDecodeError cuando en realidad vino (a).
        Ahora se revisa el Content-Type real antes de decidir como leerlo."""
        proxy = self._currentProxy()
        proxyHeaders = self._proxyHeaders(uuid.uuid4().hex)
        async with self.session.get(imagenUrl, proxy=proxy, proxy_headers=proxyHeaders) as response:
            finalUrl = str(response.url)
            if "ControlDoc/Error.jsp" in finalUrl:
                return None

            response.raise_for_status()
            content = await response.read()
            fileName = ContentTypeSniffer.fileNameFromDisposition(response.headers.get("Content-Disposition"))
            contentType = self._resolvedContentType(response, content, fileName)

            if contentType != "text/html":
                return FetchedDocument(content=content, contentType=contentType, url=finalUrl, fileName=fileName)

            html = content.decode("utf-8", errors="replace")

        match = re.search(r"temporales[\\/]([^'\"]+)", html)
        if not match or not match.group(1) or match.group(1) == ".pdf":
            snippet = html[:300].replace("\n", " ").replace("\r", "")
            raise RuntimeError(
                f"No se encontro un archivo temporal valido en la respuesta de {imagenUrl} "
                f"(url_final={finalUrl} body={snippet!r})"
            )
        fileName = match.group(1)

        parsed = urlparse(imagenUrl)
        realUrl = f"{parsed.scheme}://{parsed.netloc}/mercurio/imagenesapp/temporales/{fileName}"
        return await self._fetchBinary(realUrl, fallbackFileName=fileName)

    async def close(self):
        if self.session:
            await self.session.close()
            self.logger.info("🔌 Conexión a cliente http cerrada")