from datetime import date
import json
import logging
import uuid

from app.domain.interfaces.IHttpClient import IHttpClient
from app.domain.interfaces.IS3Manager import IS3Manager
from app.domain.interfaces.IDatabase import IDatabase
from app.domain.interfaces.IAutosDownloaderService import IAutosDownloaderService
from app.infrastructure.database.repositories.CAutoRamaRep import CAutoRamaRep
from app.infrastructure.filesystem.TempWorkspace import TempWorkspace
from app.application.dto.AutoQueueMessage import AutoQueueMessage, AutoItem


class AutosDownloaderService(IAutosDownloaderService):
    def __init__(self, httpClient: IHttpClient, tempWorkspace: TempWorkspace, db: IDatabase, s3Manager: IS3Manager, cAutoRamaRep: CAutoRamaRep):
        self.httpClient = httpClient
        self.tempWorkspace = tempWorkspace
        self.db = db
        self.s3Manager = s3Manager
        self.cAutoRamaRep = cAutoRamaRep
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
            stats = {"insertados": 0,"omitidosPorUrl": 0,"omitidosPorHash": 0,"errores": 0}
            for auto in message.autos:
                try:
                    if await self.cAutoRamaRep.checkAutoExist(conn, auto.fechaAuto, message.radicacion, auto.urlAuto, message.origen):
                        stats["omitidosPorUrl"] += 1
                        continue

                    urlFinal = await self.httpClient.resolveFinalUrl(auto.urlAuto)

                    tempFileName = f"tmp_{uuid.uuid4().hex}.pdf"
                    filePath = outputDir / tempFileName
                    await self.httpClient.downloadToFile(urlFinal, str(filePath))

                    fileHash = self.tempWorkspace.hashFile(filePath)
                    if not fileHash:
                        stats["omitidosPorHash"] += 1
                        continue

                    if fileHash in seenHashes:
                        stats["omitidosPorHash"] += 1
                        continue

                    if await self.cAutoRamaRep.existsByHash(conn, auto.fechaAuto, message.radicacion, fileHash, message.origen):
                        stats["omitidosPorHash"] += 1
                        continue

                    seenHashes.add(fileHash)

                    formattedDate = auto.fechaAuto.strftime("%d-%m-%Y")
                    maxConsecutive = await self.getMaxConsecutive(conn, auto.fechaAuto, message.radicacion, message.origen, consecutiveMap, formattedDate)

                    routeS3 = f"{formattedDate}_{message.radicacion}_{maxConsecutive}"
                    filename = f"{routeS3}.pdf"
                    filePath = filePath.rename(outputDir / filename)

                    uploaded = await self.s3Manager.uploadFile(filePath)
                    if not uploaded:
                        stats["errores"] += 1
                        continue

                    urlHashAuto = f"{auto.urlAuto}|{fileHash}"
                    if await self.cAutoRamaRep.addAutoRecord(conn, auto.fechaAuto, message.radicacion, routeS3, urlHashAuto, maxConsecutive, message.origen):
                        stats["insertados"] += 1
                except Exception as e:
                    stats["errores"] += 1
                    self.logger.error(
                        f"🔴 Error descargando auto - radicacion={message.radicacion} fecha={auto.fechaAuto} "
                        f"url={auto.urlAuto}: {e}"
                    )
                    continue

            self.logger.info(
                f"📊 Resumen descarga autos - radicacion={message.radicacion} total={len(message.autos)} "
                f"|🟢insertados={stats['insertados']} | 🔁omitidosPorUrl={stats['omitidosPorUrl']} | "
                f"| 🔗omitidosPorHash={stats['omitidosPorHash']} | 🔴errores={stats['errores']}"
            )
            await self.db.commit(conn)

            self.logger.info(f"🟢 Descarga finalizada de autos - radicacion={message.radicacion}")
        except Exception:
            self.logger.exception(f"🔴 Error procesando el lote de radicacion={message.radicacion}")
        finally:
            if conn:
                await self.db.releaseConnection(conn)


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
