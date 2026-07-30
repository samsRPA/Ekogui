from abc import ABC, abstractmethod
from typing import Optional

from app.domain.interfaces.IFileProcessor import IFileProcessor

class IProcessorFactory(ABC):
    @abstractmethod
    async def getProcessor(self, contentType: str, fileServerName:str, url:str) -> IFileProcessor:
        """Enruta segun el Content-Type/nombre de un documento obtenido por red."""
        pass

    @abstractmethod
    async def getProcessorForLocalFile(self, filePath: str) -> Optional[IFileProcessor]:
        """Enruta un archivo que ya esta en disco (ej. extraido de un
        comprimido), detectando su tipo por extension/firma binaria en vez
        de por un Content-Type de red. Retorna None si el tipo no tiene
        procesador -> el llamador debe omitir ese archivo sin abortar."""
        pass
