import os
import subprocess
from datetime import datetime
from typing import List

import fitz
from docx import Document

from app.domain.interfaces.IFileProcessor import IFileProcessor


class DocxProcessor(IFileProcessor):
    DEFAULT_EXT = ".docx"

    def _formatPdfDate(self, dt: datetime | None) -> str:
        if not dt:
            return ""
        return dt.strftime("D:%Y%m%d%H%M%S")

    def _extractMetadata(self, docxPath: str) -> dict:
        try:
            doc = Document(docxPath)
            props = doc.core_properties

            return {
                "title": props.title or "",
                "author": props.author or "",
                "subject": props.subject or "",
                "keywords": props.keywords or "",
                "creator": props.last_modified_by or "",
                "creationDate": self._formatPdfDate(props.created),
                "modDate": self._formatPdfDate(props.modified),
            }
        except Exception as e:
            raise RuntimeError(f"🔴 Error al extraer metadatos de .docx: {e}")

    def _setPdfMetadata(self, pdfPath: str, metadata: dict):
        try:
            with fitz.open(pdfPath) as doc:
                doc.set_metadata({
                    "title": metadata.get("title", ""),
                    "author": metadata.get("author", ""),
                    "subject": metadata.get("subject", ""),
                    "keywords": metadata.get("keywords", ""),
                    "creator": metadata.get("creator", ""),
                    "producer": "LibreOffice + PyMuPDF",
                    "creationDate": metadata.get("creationDate", ""),
                    "modDate": metadata.get("modDate", ""),
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
        outputDir = os.path.dirname(rawFilePath)
        baseName = os.path.splitext(os.path.basename(rawFilePath))[0]
        pdfPath = os.path.join(outputDir, f"{baseName}.pdf")

        result = subprocess.run([
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", outputDir,
            rawFilePath
        ], capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"🔴 Error al convertir Word a PDF:\n{result.stderr}")

        if not os.path.exists(pdfPath):
            raise FileNotFoundError(f"🔴 No se generó el PDF: {pdfPath}")

        metadata = self._extractMetadata(rawFilePath)
        self._setPdfMetadata(pdfPath, metadata)

        return [pdfPath]
