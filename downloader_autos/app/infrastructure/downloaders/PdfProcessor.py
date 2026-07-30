import os
import re
from typing import List

from app.domain.interfaces.IFileProcessor import IFileProcessor


class PdfProcessor(IFileProcessor):
    PDF_REGEX = re.compile(r"([^\/\\]+\.pdf)$", re.IGNORECASE)
    DEFAULT_EXT = ".pdf"

    def sanitizeFilename(self, fileName: str) -> str:
        return re.sub(r"[^\w\-.]", "_", fileName)

    async def saveRawFile(self, content: bytes, fileName: str, outputDir) -> str:
        try:
            root, ext = os.path.splitext(fileName) if fileName else ("", "")
            if not ext:
                ext = self.DEFAULT_EXT
                root = fileName or root
            root = self.sanitizeFilename(root)

            os.makedirs(outputDir, exist_ok=True)
            filePath = os.path.join(outputDir, f"{root}{ext}")

            with open(filePath, "wb") as f:
                f.write(content)

            if not os.path.exists(filePath) or os.path.getsize(filePath) == 0:
                raise RuntimeError(f"❌ Archivo descargado vacío o no encontrado en disco: {filePath}")

            return filePath
        except Exception as e:
            raise RuntimeError(f"❌ Error al guardar el archivo PDF: {e}")

    async def toPdf(self, rawFilePath: str) -> List[str]:
        # Ya es un PDF: no hay conversion, se retorna tal cual sin tocar su contenido.
        return [rawFilePath]
