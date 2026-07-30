import os
from datetime import datetime
from typing import List

import fitz
from PIL import Image, ExifTags

from app.domain.interfaces.IFileProcessor import IFileProcessor


class ImageProcessor(IFileProcessor):
    DEFAULT_EXT = ".jpg"

    def _formatPdfDate(self, dt: datetime | None) -> str:
        if not dt:
            return ""
        return dt.strftime("D:%Y%m%d%H%M%S")

    def _extractMetadata(self, imagePath: str) -> dict:
        try:
            with Image.open(imagePath) as img:
                getExif = getattr(img, "_getexif", None)
                exif = getExif() or {} if callable(getExif) else {}
                metadata = {ExifTags.TAGS.get(tag, tag): str(value) for tag, value in exif.items()}

                dateStr = (
                    metadata.get("DateTimeOriginal") or
                    metadata.get("DateTimeDigitized") or
                    metadata.get("DateTime")
                )
                try:
                    dt = datetime.strptime(dateStr, "%Y:%m:%d %H:%M:%S") if dateStr else None
                except Exception:
                    dt = None

                return {
                    "title": os.path.basename(imagePath),
                    "author": metadata.get("Artist", ""),
                    "creator": metadata.get("Software", ""),
                    "producer": f"{metadata.get('Make', '')} {metadata.get('Model', '')}".strip(),
                    "creationDate": self._formatPdfDate(dt),
                }
        except Exception:
            # La imagen no trae EXIF (comun en escaneos): se sigue sin metadata,
            # no es motivo para descartar el documento.
            return {}

    def _setPdfMetadata(self, pdfPath: str, metadata: dict):
        try:
            with fitz.open(pdfPath) as doc:
                doc.set_metadata({
                    "title": metadata.get("title", ""),
                    "author": metadata.get("author", ""),
                    "creator": metadata.get("creator", ""),
                    "producer": metadata.get("producer", "PyMuPDF"),
                    "creationDate": metadata.get("creationDate", ""),
                })

                doc.save(pdfPath, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception as e:
            raise RuntimeError(f"🔴 Error al aplicar metadatos PDF: {e}")

    async def saveRawFile(self, content: bytes, fileName: str, outputDir) -> str:
        root, ext = os.path.splitext(fileName) if fileName else ("", "")
        if not ext:
            ext = self.DEFAULT_EXT
            root = fileName or root

        os.makedirs(outputDir, exist_ok=True)
        filePath = os.path.join(outputDir, f"{root}{ext}")

        with open(filePath, "wb") as f:
            f.write(content)

        return filePath

    async def toPdf(self, rawFilePath: str) -> List[str]:
        try:
            outputDir = os.path.dirname(rawFilePath)
            baseName = os.path.splitext(os.path.basename(rawFilePath))[0]
            pdfPath = os.path.join(outputDir, f"{baseName}.pdf")

            # Se envuelve la imagen tal cual en una pagina PDF, sin OCR ni
            # reprocesar pixeles: la conversion no debe tocar el contenido.
            with fitz.open(rawFilePath) as img:
                pdfBytes = img.convert_to_pdf()

            with open(pdfPath, "wb") as f:
                f.write(pdfBytes)

            if not os.path.exists(pdfPath):
                raise FileNotFoundError(f"🔴 No se generó el PDF: {pdfPath}")

            metadata = self._extractMetadata(rawFilePath)
            self._setPdfMetadata(pdfPath, metadata)

            return [pdfPath]
        except Exception as e:
            raise RuntimeError(f"🔴 Error al convertir imagen a PDF: {e}")
