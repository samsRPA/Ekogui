import ssl
import uuid
import asyncio
import logging
from typing import AsyncIterator, List, Optional
from contextlib import asynccontextmanager

import certifi
import aiohttp
import aiofiles
from aiohttp import ClientSession, TCPConnector, ClientTimeout

from app.domain.interfaces.IHttpClient import IHttpClient
from app.domain.interfaces.IContextClient import IContextClient

class AioHttpClient(IHttpClient):
    def __init__(self, sslIntermediateCertPath: str, proxies: List[Optional[str]] = None,
                 maxConnections: int = 20, timeoutSeconds: int = 120):
        self._proxies = proxies or []
        self._index: int = 0
        self._sessionId: str = uuid.uuid4().hex
        self.session: ClientSession = None
        self.maxConnections = maxConnections
        self.timeoutSeconds = timeoutSeconds
        self.logger = logging.getLogger(__name__)
        self._sslContext = self._buildSslContext(sslIntermediateCertPath)

    def _buildSslContext(self, sslIntermediateCertPath: str) -> ssl.SSLContext:
        """auth.defensajuridica.gov.co no envia el certificado intermedio de
        su cadena (mala config TLS: solo entrega el leaf cert), asi que hay
        que agregarlo a mano al contexto SSL (ademas del bundle de certifi)
        para poder verificarla."""
        context = ssl.create_default_context(cafile=certifi.where())
        context.load_verify_locations(cafile=sslIntermediateCertPath)
        return context

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
                    ssl=self._sslContext,
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
                ssl=self._sslContext,
            ),
            timeout=timeout,
            trust_env=False,
        )

        outer = self

        class TempHttp:
            def __init__(self, session: aiohttp.ClientSession):
                self.session = session

            async def get(self, url, headers=None):
                # Cookies filtradas para esta URL puntual (respeta Path/Domain
                # via el propio matching de aiohttp). Sitios con la misma
                # cookie repetida bajo distintos paths (ej. Ekogui usa
                # XSRF-TOKEN con Path=/ekogui y Path=/ekoguims a la vez) rompen
                # la validacion CSRF si se manda el valor equivocado.
                max_attempts = max(1, len(outer._proxies))
                for attempt in range(max_attempts):
                    current_proxy = outer._currentProxy()
                    current_proxy_headers = outer._proxyHeaders(outer._sessionId)
                    scoped_cookies = self.session.cookie_jar.filter_cookies(url)
                    cookies = {k: v.value for k, v in scoped_cookies.items()}
                    try:
                        return await asyncio.wait_for(
                            self.session.get(url, headers=headers, cookies=cookies or None, proxy=current_proxy, proxy_headers=current_proxy_headers),
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

    async def downloadToFile(self, url, filePath, headers=None, chunk_size: int = 4096, maxRetries: int = 2):
        lastError = None
        for attempt in range(1, maxRetries + 1):
            proxy = self._currentProxy()
            proxyHeaders = self._proxyHeaders(uuid.uuid4().hex)
            try:
                async with self.session.get(url, headers=headers, proxy=proxy, proxy_headers=proxyHeaders) as response:
                    response.raise_for_status()
                    async with aiofiles.open(filePath, 'wb') as out_file:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            await out_file.write(chunk)
                return filePath
            except Exception as e:
                lastError = e
                self.logger.warning(f"🟡 Error en descarga, intento {attempt}/{maxRetries}, rotando proxy: {e}")
                self._advance(failed=True)

        raise RuntimeError(f"Descarga fallida tras {maxRetries} intentos - {url}: {lastError}")

    async def close(self):
        if self.session:
            await self.session.close()
            self.logger.info("🔌 Conexión a cliente http cerrada")