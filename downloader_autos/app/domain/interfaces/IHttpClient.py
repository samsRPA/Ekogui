from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from app.domain.interfaces.IContextClient import IContextClient
from app.domain.dto.FetchedDocument import FetchedDocument

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
    async def fetchDocument(self, imagenUrl: str) -> Optional[FetchedDocument]:
        """Resuelve y descarga en memoria el documento detras de la URL
        'imagen?g=<hash>' de Ekogui. A veces esa URL devuelve directo el
        archivo binario (PDF/imagen/word); otras veces devuelve una pagina
        HTML intermedia con un <embed src='...temporales\\<archivo>.pdf'>
        que hay que seguir para obtener el archivo real. En ambos casos
        retorna el documento ya descargado con su Content-Type real.
        Retorna None si Ekogui responde que el documento no existe o no
        hay permiso para verlo — el llamador debe omitir ese auto sin
        tratarlo como error."""
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