import os
import re
from datetime import datetime
from typing import List

import fitz
import pdfkit
from bs4 import BeautifulSoup

from app.domain.interfaces.IFileProcessor import IFileProcessor


class HtmlXlsProcessor(IFileProcessor):
    """Convierte a PDF contenido HTML que Ekogui a veces sirve con
    Content-Type text/plain y extension .xls (quirk conocido de reportes
    tipo ASP/webforms: el 'Excel' en realidad es una tabla HTML)."""

    def _formatPdfDate(self, dt: datetime | None) -> str:
        if not dt:
            return ""
        return dt.strftime("D:%Y%m%d%H%M%S")

    def _extractMetadata(self, htmlPath: str) -> dict:
        """Intenta extraer solo la fecha del reporte, si el HTML la trae en
        el formato esperado. Si no la trae, se sigue sin metadata: no es
        motivo para descartar el documento."""
        try:
            with open(htmlPath, "r", encoding="utf-8", errors="replace") as f:
                soup = BeautifulSoup(f, "html.parser")

            dateSpan = soup.find("span", {"id": "LblSubTitulo"})
            if not dateSpan:
                return {}

            match = re.search(r"(\d{2}/\d{2}/\d{4})", dateSpan.text)
            if not match:
                return {}

            dt = datetime.strptime(match.group(1), "%d/%m/%Y")
            formattedDate = self._formatPdfDate(dt)

            return {
                "creationDate": formattedDate,
                "modDate": formattedDate,
            }
        except Exception:
            return {}

    def _setPdfMetadata(self, pdfPath: str, metadata: dict):
        try:
            with fitz.open(pdfPath) as doc:
                currentMetadata = doc.metadata or {}
                currentMetadata.update({
                    "creationDate": metadata.get("creationDate", ""),
                    "modDate": metadata.get("modDate", ""),
                })
                doc.set_metadata(currentMetadata)
                doc.save(pdfPath, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception as e:
            raise RuntimeError(f"🔴 Error al aplicar metadatos PDF: {e}")

    async def saveRawFile(self, content: bytes, fileName: str, outputDir) -> str:
        root = os.path.splitext(fileName)[0] if fileName else "documento"

        os.makedirs(outputDir, exist_ok=True)
        filePath = os.path.join(outputDir, f"{root}.html")

        with open(filePath, "wb") as f:
            f.write(content)

        return filePath

    async def toPdf(self, rawFilePath: str) -> List[str]:
        outputDir = os.path.dirname(rawFilePath)
        baseName = os.path.splitext(os.path.basename(rawFilePath))[0]
        pdfPath = os.path.join(outputDir, f"{baseName}.pdf")

        options = {
            "orientation": "Landscape",
            "page-size": "Letter",
            "encoding": "UTF-8",
            "margin-top": "5mm",
            "margin-bottom": "5mm",
            "margin-left": "5mm",
            "margin-right": "5mm",
        }

        try:
            pdfkit.from_file(rawFilePath, pdfPath, options=options)
        except Exception as e:
            raise RuntimeError(f"🔴 Error al convertir HTML a PDF: {e}")

        if not os.path.exists(pdfPath):
            raise FileNotFoundError(f"🔴 No se generó el PDF: {pdfPath}")

        metadata = self._extractMetadata(rawFilePath)
        if metadata:
            self._setPdfMetadata(pdfPath, metadata)

        return [pdfPath]
