import os
from typing import Callable, Optional

from app.domain.interfaces.IProcessorFactory import IProcessorFactory
from app.domain.interfaces.IFileProcessor import IFileProcessor
from app.domain.dto.ContentTypeSniffer import ContentTypeSniffer


class ProcessorFactory(IProcessorFactory):
    def __init__(self, processorMap: dict[str, Callable[[], IFileProcessor]]):
        self.processorMap = processorMap

    async def getProcessor(self, contentType: str, fileServerName: str, url: str) -> IFileProcessor:
        contentTypeKey = (contentType or "").split(";")[0].strip().lower()
        ext = os.path.splitext(fileServerName)[1].lstrip(".").lower() if fileServerName else None

        # Quirk conocido de SGDEA/ASP: un reporte "Excel" que en realidad es
        # una tabla HTML servida con extension .xls y Content-Type text/plain.
        if contentTypeKey == "text/plain" and ext == "xls":
            return self.processorMap[ContentTypeSniffer.HTML_MARKER]()

        if contentTypeKey in self.processorMap:
            return self.processorMap[contentTypeKey]()

        # Imagenes deshabilitadas a pedido (ver Dependencies.py): se omiten
        # en lugar de fallar como un tipo no soportado.
        if contentTypeKey.startswith("image/"):
            return None

        raise ValueError(f"No hay procesador definido para tipo '{contentType}' y url '{url}'")

    async def getProcessorForLocalFile(self, filePath: str) -> Optional[IFileProcessor]:
        contentType = ContentTypeSniffer.forLocalFile(filePath)
        if not contentType:
            return None
        builder = self.processorMap.get(contentType)
        return builder() if builder else None
