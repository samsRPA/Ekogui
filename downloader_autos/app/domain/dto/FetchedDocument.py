from dataclasses import dataclass
from typing import Optional


@dataclass
class FetchedDocument:
    """Documento ya descargado en memoria, listo para que un IFileProcessor
    lo guarde en disco y lo convierta a PDF. contentType es el tipo real
    (declarado por el servidor o inferido por firma binaria si el header
    venia vacio/incorrecto), no necesariamente el que Ekogui declaro."""

    content: bytes
    contentType: str
    url: str
    fileName: Optional[str] = None
