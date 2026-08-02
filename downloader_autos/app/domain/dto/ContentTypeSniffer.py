import os
import re
from typing import ClassVar, Dict, List, Optional, Tuple


class ContentTypeSniffer:
    """Infiere el Content-Type real de un documento a partir de su firma
    binaria/extension y extrae el nombre de archivo de un header
    Content-Disposition.

    Ekogui a veces declara un Content-Type vacio o generico
    (application/octet-stream) para archivos que en realidad son un PDF,
    una imagen, un Word/Excel o un comprimido. Sin esto, el codigo asumia
    que la respuesta siempre era HTML y tronaba con UnicodeDecodeError al
    intentar decodificar bytes binarios como texto."""

    UNRELIABLE_CONTENT_TYPES: ClassVar[set] = {"", "application/octet-stream", "binary/octet-stream"}

    # Marcador interno (no es un MIME type real) para contenido HTML que
    # llega declarado como texto/xls -> quirk conocido de SGDEA/ASP donde un
    # reporte "Excel" en realidad es una tabla HTML con extension .xls.
    HTML_MARKER: ClassVar[str] = "htmlXsl"

    _MAGIC_SIGNATURES: ClassVar[List[Tuple[bytes, str]]] = [
        (b"%PDF-", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"BM", "image/bmp"),
        (b"II*\x00", "image/tiff"),
        (b"MM\x00*", "image/tiff"),
        (b"Rar!\x1a\x07", "application/x-rar-compressed"),
        (b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
        # PK\x03\x04 (zip local file header) es ambiguo: lo comparten .zip,
        # .docx y .xlsx (Office Open XML es zip por dentro). Se resuelve por
        # extension en refineByExtension/forLocalFile.
        (b"PK\x03\x04", "application/zip"),
        # OLE2 tambien es ambiguo: lo comparten .doc y .xls viejos.
        (b"\xd0\xcf\x11\xe0", "application/msword"),
    ]

    _EXTENSION_CONTENT_TYPES: ClassVar[Dict[str, str]] = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docm": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsm": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".zip": "application/zip",
        ".rar": "application/x-rar-compressed",
        ".7z": "application/x-7z-compressed",
    }

    # Extensiones cuya firma binaria (ver arriba) es ambigua entre varios
    # formatos; se desambigua prefiriendo la extension declarada. Los
    # formatos Office "macro-enabled" (.xlsm/.docm) son el mismo contenedor
    # zip que su version normal; se convierten igual (solo se renderiza a
    # PDF, nunca se ejecutan macros).
    _ZIP_FAMILY_BY_EXT: ClassVar[Dict[str, str]] = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docm": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsm": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".zip": "application/zip",
    }
    _OLE2_FAMILY_BY_EXT: ClassVar[Dict[str, str]] = {
        ".doc": "application/msword",
        ".xls": "application/vnd.ms-excel",
    }

    _DISPOSITION_FILENAME_RE = re.compile(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", re.IGNORECASE)

    @classmethod
    def sniffContentType(cls, content: bytes) -> Optional[str]:
        for signature, contentType in cls._MAGIC_SIGNATURES:
            if content.startswith(signature):
                return contentType
        return None

    @classmethod
    def isUnreliable(cls, contentType: str) -> bool:
        return (contentType or "").strip().lower() in cls.UNRELIABLE_CONTENT_TYPES

    @classmethod
    def byExtension(cls, fileName: Optional[str]) -> Optional[str]:
        """Ultimo fallback cuando ni el Content-Type declarado ni la firma
        binaria (sniffContentType) permiten identificar el archivo: se usa
        la extension del nombre real (Content-Disposition o el archivo bajo
        temporales/) contra el mismo mapa de forLocalFile."""
        if not fileName:
            return None
        ext = os.path.splitext(fileName)[1].lower()
        return cls._EXTENSION_CONTENT_TYPES.get(ext)

    @classmethod
    def refineByExtension(cls, contentType: str, fileName: Optional[str]) -> str:
        """PK\\x03\\x04 y el header OLE2 son ambiguos entre varios formatos
        (zip/docx/xlsx y doc/xls respectivamente). Si el sniff cayo en el
        valor generico de esa familia pero el nombre de archivo trae una
        extension mas especifica, se prefiere esa."""
        if not fileName:
            return contentType
        ext = os.path.splitext(fileName)[1].lower()
        if contentType == "application/zip":
            return cls._ZIP_FAMILY_BY_EXT.get(ext, contentType)
        if contentType == "application/msword":
            return cls._OLE2_FAMILY_BY_EXT.get(ext, contentType)
        return contentType

    @classmethod
    def fileNameFromDisposition(cls, disposition: Optional[str]) -> Optional[str]:
        if not disposition:
            return None
        match = cls._DISPOSITION_FILENAME_RE.search(disposition)
        return match.group(1).strip() if match else None

    @classmethod
    def _looksLikeHtml(cls, filePath: str) -> bool:
        try:
            with open(filePath, "rb") as f:
                head = f.read(1024).lstrip().lower()
        except OSError:
            return False
        return head.startswith(b"<html") or head.startswith(b"<!doctype html") or b"<table" in head

    @classmethod
    def forLocalFile(cls, filePath: str) -> Optional[str]:
        """Determina el Content-Type de un archivo ya en disco (ej. uno
        extraido de un comprimido), por extension y, si hace falta, por
        firma binaria. Nunca hace una llamada de red."""
        ext = os.path.splitext(filePath)[1].lower()

        if ext in (".htm", ".html"):
            return cls.HTML_MARKER
        if ext == ".xls" and cls._looksLikeHtml(filePath):
            return cls.HTML_MARKER

        contentType = cls._EXTENSION_CONTENT_TYPES.get(ext)
        if contentType:
            return contentType

        try:
            with open(filePath, "rb") as f:
                head = f.read(64)
        except OSError:
            return None

        sniffed = cls.sniffContentType(head)
        return cls.refineByExtension(sniffed, filePath) if sniffed else None
