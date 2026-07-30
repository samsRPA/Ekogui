from pathlib import Path
from abc import ABC, abstractmethod
from typing import List


class IFileProcessor(ABC):
    @abstractmethod
    async def saveRawFile(self, content: bytes, fileName: str, outputDir: Path) -> str:
        """Guarda en disco el contenido ya descargado, tal cual llego (sin alterarlo)."""
        ...

    @abstractmethod
    async def toPdf(self, rawFilePath: str) -> List[str]:
        """Convierte el archivo crudo a uno o mas PDF. Solo cambia el
        formato/contenedor, nunca el contenido (texto/imagen) del
        documento original. La mayoria de procesadores producen exactamente
        un PDF; un comprimido puede producir varios (uno por cada archivo
        soportado que traiga adentro, sin contar el comprimido en si)."""
        ...
