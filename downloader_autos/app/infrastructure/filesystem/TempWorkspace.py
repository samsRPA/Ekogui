import shutil
import hashlib
import logging
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

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
