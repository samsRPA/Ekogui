import shutil
import hashlib
import logging
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

import fitz

class TempWorkspace:
    def __init__(self, basePath: Path) -> None:
        self.basePath = basePath
        self.logger = logging.getLogger(__name__)

    def hashFile(self, filePath: Path, chunkSize: int = 8192) -> str:
        sha256 = hashlib.sha256()
        with open(filePath, "rb") as f:
            for chunk in iter(lambda: f.read(chunkSize), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def isValidPdf(self, filePath: Path) -> bool:
        """Valida que el archivo descargado sea realmente un PDF abrible y
        con al menos una pagina. Ekogui a veces responde con una pagina
        HTML intermedia en vez del PDF; esto evita subir esa basura a S3
        disfrazada de '.pdf'.
        Se usa fitz en vez de solo chequear el magic header '%PDF-' en el
        byte 0: algunos PDF validos traen bytes delante (BOM, salto de
        linea, metadata del generador) que un chequeo de posicion fija
        rechazaria como invalidos aunque el archivo abra perfecto en
        cualquier lector."""
        try:
            with fitz.open(filePath) as doc:
                return doc.page_count > 0
        except Exception:
            return False

    def _createFolder(self, folderName: str) -> Path:
        path = self.basePath / folderName
        path.mkdir(parents=True, exist_ok=True)
        return path

    def buildTypeDir(self, outputDir: Path, typePublication: str, formattedDate: str, records) -> Path:
        path = outputDir / typePublication / formattedDate / str(records)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _deleteFolder(self, folderName: str) -> None:
        path = self.basePath / folderName
        if path.exists() and path.is_dir():
            try:
                shutil.rmtree(path)
            except Exception as e:
                self.logger.error(f"🔴 Error al eliminar la carpeta {path}: {e}")

    @contextmanager
    def useTempFolder(self, folderName: str) -> Iterator[Path]:
        path = self._createFolder(folderName)
        try:
            yield path
        finally:
            self._deleteFolder(folderName)
            #pass
