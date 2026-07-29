from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.domain.interfaces.IContextClient import IContextClient

class IHttpClient(ABC):
    @abstractmethod
    async def init(self):
        """Inicializa la sesión HTTP persistente."""
        ...

    @abstractmethod
    async def getHeaders(self, url: str, headers: dict = None) -> dict:
        """Realiza un HEAD request y retorna los headers de la respuesta."""
        ...

    @abstractmethod
    async def detectMimeType(self, url: str) -> str | None:
        """Detecta la extensión del archivo en una URL basándose en el Content-Type."""
        ...

    @abstractmethod
    async def downloadToFile(self, url: str, filePath: str, headers: dict = None, chunk_size: int = 4096, maxRetries: int = 2) -> str:
        """Descarga un archivo desde una URL y lo guarda en disco."""
        ...

    @abstractmethod
    async def resolveFinalUrl(self, imagenUrl: str) -> str:
        """Resuelve la URL 'imagen?g=<hash>' de Ekogui (estable, no expira)
        a la URL final y ephemera del PDF ('.../temporales/<archivo>.pdf')
        que el SGD genera al visitarla. Esa URL final es la que hay que
        descargar; la 'imagen?g=' por si sola solo devuelve un HTML
        intermedio con un <embed> apuntando al PDF real."""
        ...

    @abstractmethod
    async def contextClient(self) -> AsyncIterator[IContextClient]:
        """Context manager que provee un cliente HTTP temporal con proxy activo."""
        ...

    @abstractmethod
    def invalidateProxy(self):
        """Marca el proxy actual como fallido y rota al siguiente."""
        ...

    @abstractmethod
    async def close(self):
        """Cierra la sesión HTTP."""
        ...