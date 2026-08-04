from datetime import date
from pathlib import Path
import json
import logging
import os
import uuid

from app.domain.interfaces.IHttpClient import IHttpClient
from app.domain.interfaces.IS3Manager import IS3Manager
from app.domain.interfaces.IDatabase import IDatabase
from app.domain.interfaces.IAutosDownloaderService import IAutosDownloaderService
from app.domain.interfaces.IProcessorFactory import IProcessorFactory
from app.infrastructure.database.repositories.CAutoRamaRep import CAutoRamaRep
from app.infrastructure.filesystem.TempWorkspace import TempWorkspace
from app.application.dto.AutoQueueMessage import AutoQueueMessage, AutoItem


class AutosDownloaderService(IAutosDownloaderService):
    def __init__(self, httpClient: IHttpClient, tempWorkspace: TempWorkspace, db: IDatabase, s3Manager: IS3Manager, cAutoRamaRep: CAutoRamaRep, processorFactory: IProcessorFactory):
        self.httpClient = httpClient
        self.tempWorkspace = tempWorkspace
        self.db = db
        self.s3Manager = s3Manager
        self.cAutoRamaRep = cAutoRamaRep
        self.processorFactory = processorFactory
        self.logger = logging.getLogger(__name__)

    async def handleMessage(self, body: bytes) -> None:
        try:
            message = self._parseMessage(body)
        except json.JSONDecodeError:
            self.logger.error("🔴 Mensaje inválido: JSON malformado")
            raise

        with self.tempWorkspace.useTempFolder(message.folderName) as outputDir:
            await self._processAutos(message, outputDir)

    def _parseMessage(self, body: bytes) -> AutoQueueMessage:
        return AutoQueueMessage.fromRaw(json.loads(body.decode("utf-8")))

    def _resolveUrlAutoName(self, auto: AutoItem) -> str:
        """Ultimo respaldo: urlAutoName nunca debe llegar vacio a la BD, sin
        importar que traiga el mensaje."""
        if auto.urlAutoName:
            return auto.urlAutoName
        return f"{auto.urlAuto}#{auto.namePDF}" if auto.namePDF else auto.urlAuto

    async def _processAutos(self, message: AutoQueueMessage, outputDir) -> None:
        conn = None
        try:
            conn = await self.db.acquireConnection()

            self.logger.info(
                f"⬇️ Iniciando descarga de autos - radicacion={message.radicacion} despacho={message.despacho} "
                f"origen={message.origen} total={len(message.autos)}"
            )

            consecutiveMap = {}
            seenHashes = set()
            stats = {"insertados": 0,"omitidosPorUrl": 0,"omitidosPorHash": 0,"omitidosPorPdfInvalido": 0,"omitidosPorNoDisponible": 0,"errores": 0}
            for auto in message.autos:
                try:
                    urlAutoName = self._resolveUrlAutoName(auto)
                    if await self.cAutoRamaRep.checkAutoExist(conn, auto.fechaAuto, message.radicacion, urlAutoName, message.origen):
                        stats["omitidosPorUrl"] += 1
                        continue

                    fetched = await self.httpClient.fetchDocument(auto.urlAuto)
                    if fetched is None:
                        stats["omitidosPorNoDisponible"] += 1
                        self.logger.warning(
                            f"🟡 Documento no disponible en Ekogui (sin permiso o no existe) - "
                            f"radicacion={message.radicacion} fecha={auto.fechaAuto} url={auto.urlAuto}"
                        )
                        continue

                    processor = await self.processorFactory.getProcessor(fetched.contentType, fetched.fileName, auto.urlAuto)

                    fetchedExt = os.path.splitext(fetched.fileName)[1] if fetched.fileName else ""
                    tempFileName = f"tmp_{uuid.uuid4().hex}{fetchedExt}"
                    rawFilePath = await processor.saveRawFile(fetched.content, tempFileName, outputDir)
                    pdfPaths = await processor.toPdf(rawFilePath)

                    if not pdfPaths:
        
                        stats["omitidosPorPdfInvalido"] += 1
                        self.logger.warning(
                            f"🟡 Sin documentos convertibles - radicacion={message.radicacion} "
                            f"fecha={auto.fechaAuto} url={auto.urlAuto}"
                        )
                        continue

                 
                    isFromCompressed = len(pdfPaths) > 1
                    for pdfPath in pdfPaths:
                        pdfPath = Path(pdfPath)
            
                        childId = pdfPath.stem if isFromCompressed else None
                        await self._storeConvertedPdf(conn, message, auto, outputDir, pdfPath, consecutiveMap, seenHashes, stats, childId
                        )

                    if isFromCompressed:
                        await self.cAutoRamaRep.addAutoRecord(
                            conn, auto.fechaAuto, message.radicacion, None, urlAutoName, None, message.origen,
                            estadoDescarga="SI", tipoDocumento=fetchedExt.lstrip(".").lower()
                        )
                except Exception as e:
                    stats["errores"] += 1
                    self.logger.error(
                        f"🔴 Error descargando auto - radicacion={message.radicacion} fecha={auto.fechaAuto} "
                        f"url={auto.urlAuto}: {e}"
                    )
                    continue

            await self.db.commit(conn)
            self.logger.info(
                f"📊 Resumen descarga autos - radicacion={message.radicacion} total={len(message.autos)} "
                f"|🟢insertados={stats['insertados']} | 🔁omitidosPorUrl={stats['omitidosPorUrl']} | "
                f"| 🔗omitidosPorHash={stats['omitidosPorHash']} | 📄omitidosPorPdfInvalido={stats['omitidosPorPdfInvalido']} "
                f"| 🚫omitidosPorNoDisponible={stats['omitidosPorNoDisponible']} | 🔴errores={stats['errores']}"
            )

            self.logger.info(f"🟢 Descarga finalizada de autos - radicacion={message.radicacion}")
        except Exception:
            self.logger.exception(f"🔴 Error procesando el lote de radicacion={message.radicacion}")
        finally:
            if conn:
                await self.db.releaseConnection(conn)


    async def _storeConvertedPdf(self, conn, message: AutoQueueMessage, auto: AutoItem, outputDir, filePath: Path,
                                  consecutiveMap: dict, seenHashes: set, stats: dict, childId: str = None) -> None:
        """Valida, deduplica, sube a S3 y registra en BD un PDF ya
        convertido. Se llama una vez por cada PDF resultante de un auto:
        normalmente uno, pero un comprimido produce uno por cada archivo
        soportado que traiga adentro -> cada uno conserva el radicado y la
        fecha del auto, pero recibe su propio consecutivo."""
        if not self.tempWorkspace.isValidPdf(filePath):
            stats["omitidosPorPdfInvalido"] += 1
            self.logger.warning(
                f"🟡 PDF invalido descartado - radicacion={message.radicacion} fecha={auto.fechaAuto} "
                f"url={auto.urlAuto} archivo={filePath.name}"
            )
            return

        fileHash = self.tempWorkspace.hashFile(filePath)
        if not fileHash:
            stats["omitidosPorHash"] += 1
            return

        baseUrlAutoName = self._resolveUrlAutoName(auto)
        autoUrl = f"{baseUrlAutoName}#{childId}" if childId else baseUrlAutoName
        urlHashAuto = f"{autoUrl}|{fileHash}"
        
        if fileHash in seenHashes:
            stats["omitidosPorHash"] += 1
           
            return

        if await self.cAutoRamaRep.existsByHash(conn, auto.fechaAuto, message.radicacion, fileHash, message.origen):
            stats["omitidosPorHash"] += 1
            await self.cAutoRamaRep.addAutoRecord(conn, auto.fechaAuto, message.radicacion, None, urlHashAuto, None, message.origen, estadoDescarga="NO")
            return

        seenHashes.add(fileHash)

        formattedDate = auto.fechaAuto.strftime("%d-%m-%Y")
        maxConsecutive = await self.getMaxConsecutive(conn, auto.fechaAuto, message.radicacion, message.origen, consecutiveMap, formattedDate)

        routeS3 = f"{formattedDate}_{message.radicacion}_{maxConsecutive}"
        filename = f"{routeS3}.pdf"
        finalPath = filePath.rename(outputDir / filename)

        uploaded = await self.s3Manager.uploadFile(finalPath)
        if not uploaded:
            stats["errores"] += 1
            return

        if await self.cAutoRamaRep.addAutoRecord(conn, auto.fechaAuto, message.radicacion, routeS3, urlHashAuto, maxConsecutive, message.origen):
            stats["insertados"] += 1

    async def getMaxConsecutive(self, conn, autoDate: date, radicado: str, origin: str, consecutiveMap, formattedDate):
        try:

            mapKey = f"{radicado}-{ formattedDate}"
            if mapKey in consecutiveMap:
                consecutivo = consecutiveMap[mapKey]
                consecutiveMap[mapKey] += 1
            else:
                maxConsecutive = await self.cAutoRamaRep.maxConsecutive(conn, autoDate, radicado, origin)
                consecutivo = maxConsecutive + 1
                consecutiveMap[mapKey] = consecutivo + 1

            return consecutivo

        except Exception as e :
            self.logger.exception(f"🔴 Error al obtener el maximo consecutivo {e}")
            return None
