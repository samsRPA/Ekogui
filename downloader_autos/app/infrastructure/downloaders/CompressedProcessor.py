import os
import logging
import zipfile
from pathlib import Path
from typing import List, Optional

import py7zr
import rarfile

from app.domain.interfaces.IFileProcessor import IFileProcessor
from app.domain.interfaces.IProcessorFactory import IProcessorFactory

# unrar es de licencia no-libre y no esta en los repos "main" de Debian; unar
# (the-unarchiver) si, y rarfile lo soporta como herramienta externa.
rarfile.UNRAR_TOOL = "unar"


class CompressedProcessor(IFileProcessor):
    """Extrae zip/rar/7z (incluyendo subcarpetas) y convierte a PDF cada
    archivo soportado que traiga adentro, usando la misma fabrica de
    procesadores. El comprimido en si nunca se sube ni recibe consecutivo,
    solo los PDF resultantes de sus archivos internos. Soporta un
    comprimido dentro de otro (vuelve a pasar por la fabrica), con un tope
    de profundidad para no quedar atrapado en un zip-bomb."""

    DEFAULT_EXT = ".zip"
    MAX_DEPTH = 5
    _EXTRACT_SUFFIX = "_extracted"

    def __init__(self, processorFactory: IProcessorFactory):
        self.processorFactory = processorFactory
        self.logger = logging.getLogger(__name__)

    def _detectArchiveExt(self, content: bytes) -> Optional[str]:
        if content.startswith(b"PK\x03\x04"):
            return ".zip"
        if content.startswith(b"Rar!\x1a\x07"):
            return ".rar"
        if content.startswith(b"7z\xbc\xaf\x27\x1c"):
            return ".7z"
        return None

    async def saveRawFile(self, content: bytes, fileName: str, outputDir) -> str:
        root, declaredExt = os.path.splitext(fileName) if fileName else ("", "")
        ext = self._detectArchiveExt(content) or declaredExt or self.DEFAULT_EXT
        root = root or "comprimido"

        os.makedirs(outputDir, exist_ok=True)
        filePath = os.path.join(outputDir, f"{root}{ext}")

        with open(filePath, "wb") as f:
            f.write(content)

        return filePath

    def _assertSafeMembers(self, names: List[str], extractDir: str) -> None:
        """Bloquea zip-slip: ningun miembro puede resolver fuera de extractDir
        (rutas absolutas o con '..')."""
        base = Path(extractDir).resolve()
        for name in names:
            target = (Path(extractDir) / name).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError(f"Ruta insegura dentro del comprimido (zip-slip): {name!r}")

    def _extract(self, rawFilePath: str, extractDir: str) -> None:
        if rawFilePath.endswith(".zip"):
            with zipfile.ZipFile(rawFilePath) as archive:
                self._assertSafeMembers(archive.namelist(), extractDir)
                archive.extractall(extractDir)
        elif rawFilePath.endswith(".rar"):
            with rarfile.RarFile(rawFilePath) as archive:
                self._assertSafeMembers(archive.namelist(), extractDir)
                archive.extractall(extractDir)
        elif rawFilePath.endswith(".7z"):
            with py7zr.SevenZipFile(rawFilePath, mode="r") as archive:
                self._assertSafeMembers(archive.getnames(), extractDir)
                archive.extractall(path=extractDir)
        else:
            raise ValueError(f"Formato de archivo comprimido no soportado: {rawFilePath}")

    async def toPdf(self, rawFilePath: str) -> List[str]:
        depth = str(rawFilePath).count(self._EXTRACT_SUFFIX)
        if depth >= self.MAX_DEPTH:
            self.logger.warning(
                f"🟡 Limite de anidamiento de comprimidos alcanzado ({self.MAX_DEPTH}), se omite {rawFilePath}"
            )
            return []

        extractDir = f"{rawFilePath}{self._EXTRACT_SUFFIX}"
        try:
            self._extract(rawFilePath, extractDir)
        except Exception as e:
            raise RuntimeError(f"🔴 Error al extraer el archivo comprimido {rawFilePath}: {e}")

        pdfPaths: List[str] = []
        for filePath in sorted(Path(extractDir).rglob("*")):
            if not filePath.is_file():
                continue

            processor = await self.processorFactory.getProcessorForLocalFile(str(filePath))
            if processor is None:
                self.logger.warning(f"🟡 Archivo sin procesador dentro de comprimido, se omite: {filePath.name}")
                continue

            try:
                pdfPaths.extend(await processor.toPdf(str(filePath)))
            except Exception:
                self.logger.exception(f"🔴 Error convirtiendo archivo dentro de comprimido, se omite: {filePath.name}")
                continue

        return pdfPaths
