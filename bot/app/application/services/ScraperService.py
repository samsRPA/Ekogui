import json
import logging

from app.application.dto.AutoDto import AutoDto, AutoItemDto
from app.application.dto.ActuacionDto import ActuacionDto
from app.application.dto.EkoguiReq import EkoguiReq, ProcesoItem
from app.domain.interfaces.IEkoguiScraper import IEkoguiScraper
from app.domain.interfaces.IHttpClient import IHttpClient
from app.domain.interfaces.IScraperService import IScraperService
from app.domain.interfaces.IBrokerProducer import IBrokerProducer
from app.domain.interfaces.IDatabase import IDatabase
from app.domain.interfaces.IDataBaseService import IDataBaseService

# BD / S3 quedan disponibles para cuando se reactive la insercion/subida; por
# ahora el scraper solo descarga y guarda en local (ver _process /
# _processProceso mas abajo, donde esos pasos quedan comentados sin borrar
# los archivos IDatabase/IDataBaseService/IS3Manager/OracleDB/S3Manager).
# from app.domain.interfaces.IDatabase import IDatabase
# from app.domain.interfaces.IDataBaseService import IDataBaseService
# from app.domain.interfaces.IS3Manager import IS3Manager


class ScraperService(IScraperService):
    def __init__(self, scraper: IEkoguiScraper, httpClient: IHttpClient,
                 db:IDatabase, dataBaseService:IDataBaseService,  producer:IBrokerProducer,
                 collProducer:IBrokerProducer):
        self.scraper = scraper
        self.httpClient = httpClient
        self.db = db
        self.dataBaseService = dataBaseService
        self.producer = producer
        self.collProducer = collProducer
        self.logger = logging.getLogger(__name__)

    async def handleMessage(self, body: bytes) -> None:
        try:
            data = self._parseMessage(body)
            async with self.httpClient.contextClient() as client:
                await self._process(data, client)
        except json.JSONDecodeError:
            self.logger.error("🔴 Mensaje inválido: JSON malformado")
            raise
        except Exception:
            self.logger.exception("🔴 Error procesando mensaje")
            raise

    def _parseMessage(self, body: bytes) -> EkoguiReq:
        return EkoguiReq.fromRaw(json.loads(body.decode("utf-8")))

    async def _process(self, data: EkoguiReq, client) -> None:
        self.logger.info(
            f"🌐 Iniciando scraper - entidadId={data.entidadId} ({data.entidadNombre}) - {len(data.procesos)} proceso(s)"
        )
        idToken = await self.scraper.iniciarSesionEntidad(client, data.entidadId)

        totalDocumentos = 0
        totalActuaciones = 0
        for proceso in data.procesos:
            try:
                documentosCount, actuacionesCount = await self._processProceso(proceso, client, idToken)
                totalDocumentos += documentosCount
                totalActuaciones += actuacionesCount
            except Exception:
                self.logger.exception(
                    f"🔴 Error procesando procesoId={proceso.procesoId} ({proceso.numeroProceso}); se continua con el resto del lote"
                )

        self.logger.info(
            f"🟢 Scraper terminado de este lote - entidadId={data.entidadId} ({data.entidadNombre}) -> "
            f"{totalDocumentos} documento(s), {totalActuaciones} actuacion(es) extraidas"
        )

    def _buildActuacionDto(self, proceso: ProcesoItem, doc: dict) -> ActuacionDto:
        """Arma el registro de actuacion (destino RAMA), uno por documento
        descargado, listo para publicar en COLL_QUEUE_NAME:
        - RADICADO_RAMA: 'Codigo unico del proceso' -> numeroProceso.
        - COD_DESPACHO_RAMA: 'Despacho inicial' -> despachoInicialNombre.
        - FECHA_ACTUACION: 'Fecha de radicacion en SGD o cargue del documento' -> fechaRadicado.
        - ACTUACION_RAMA: 'Tipo de documento' -> tipoAnexoDescripcion.
        - ANOTACION_RAMA / ORIGEN_DATOS: valores fijos."""
        return ActuacionDto(
            RADICADO_RAMA=proceso.numeroProceso,
            COD_DESPACHO_RAMA=proceso.despachoInicialNombre,
            FECHA_ACTUACION=doc.get("fechaRadicado"),
            ACTUACION_RAMA=doc.get("tipoAnexoDescripcion"),
        )

    def _buildAutoItemDto(self, doc: dict, urlAuto: str) -> AutoItemDto:
        return AutoItemDto(
            fechaAuto=doc.get("fechaRadicado"),
            urlAuto=urlAuto,
        )

    def _buildAutoDto(self, proceso: ProcesoItem, autos: list[AutoItemDto]) -> AutoDto:
        return AutoDto(
            radicacion=proceso.numeroProceso,
            despacho=proceso.despachoInicialNombre,
            origen="EKOGUI",
            autos=autos,
        )

    async def _publishAutos(self, proceso: ProcesoItem, autos: list[AutoItemDto]) -> int:
        """Valida existencia y publica el lote de autos de UN proceso (un
        solo mensaje con los autos nuevos). La conexion a BD se adquiere
        aqui (no antes ni durante el scraping) y se libera al terminar; si
        no se pudo adquirir, se publican todos sin validar (fail-open:
        downloader_autos vuelve a validar existencia antes de descargar/
        insertar)."""
        if not self.producer or not autos:
            return 0

        conn = None
        try:
            conn = await self.db.acquireConnection()
        except Exception:
            self.logger.exception(
                "🔴 Error adquiriendo conexion a BD; se publican los autos sin validar existencia"
            )

        autosNuevos: list[AutoItemDto] = []
        try:
            for autoItem in autos:
                existe = False
                if conn:
                    existe = await self.dataBaseService.autoExiste(
                        conn, proceso.numeroProceso, autoItem.fechaAuto, autoItem.urlAuto
                    )
                if existe:
                    # self.logger.info(
                    #     f"🔁 auto ya existente en RAMA radicado={proceso.numeroProceso} "
                    #     f"url={autoItem.urlAuto}; no se publica"
                    # )
                    continue
                autosNuevos.append(autoItem)
        finally:
            if conn:
                await self.db.releaseConnection(conn)

        if not autosNuevos:
            return 0

        autoDto = self._buildAutoDto(proceso, autosNuevos)
        try:
            await self.producer.publishMessage(autoDto.model_dump(mode="json"), priority=1)
        except Exception:
            self.logger.exception(f"🔴 Error publicando lote de autos radicacion={autoDto.radicacion} en {self.producer.queueName}")
            return 0

        return len(autosNuevos)

    async def _publishActuaciones(self, actuaciones: list[ActuacionDto]) -> int:
        if not actuaciones:
            return 0

        conn = None
        try:
            conn = await self.db.acquireConnection()
        except Exception:
            self.logger.exception(
                "🔴 Error adquiriendo conexion a BD; se publican las actuaciones sin validar existencia"
            )

        publicadas = 0
        vistas: set[tuple] = set()
        try:
            for actuacionDto in actuaciones:
                clave = (
                    actuacionDto.RADICADO_RAMA,
                    actuacionDto.FECHA_ACTUACION,
                    actuacionDto.ACTUACION_RAMA,
                    actuacionDto.ANOTACION_RAMA,
                    actuacionDto.ORIGEN_DATOS,
                )
                if clave in vistas:
                    continue
                vistas.add(clave)

                existe = False
                if conn:
                    existe = await self.dataBaseService.actuacionExiste(
                        conn,
                        actuacionDto.RADICADO_RAMA,
                        actuacionDto.FECHA_ACTUACION,
                        actuacionDto.ACTUACION_RAMA,
                        actuacionDto.ANOTACION_RAMA,
                    )
                if existe:
                    # self.logger.info(
                    #     f"🔁 actuacion ya existente en RAMA radicado={actuacionDto.RADICADO_RAMA} "
                    #     f"actuacion={actuacionDto.ACTUACION_RAMA}; no se publica"
                    # )
                    continue

                try:
                    await self.collProducer.publishMessage(actuacionDto.model_dump(mode="json"))
                    publicadas += 1
                except Exception:
                    self.logger.exception(
                        f"🔴 Error publicando actuacion radicado={actuacionDto.RADICADO_RAMA} en {self.collProducer.queueName}"
                    )
        finally:
            if conn:
                await self.db.releaseConnection(conn)

        return publicadas

    async def _processProceso(self, proceso: ProcesoItem, client, idToken: str) -> tuple[int, int]:
        documentos = await self.scraper.listarDocumentosProceso(client, idToken, proceso.procesoId)
        if not documentos:
            self.logger.warning(
                f"🟡 radicado={proceso.numeroProceso} (procesoId={proceso.procesoId}) sin documentos; se omite."
            )
            return 0, 0

        autos: list[AutoItemDto] = []
        actuaciones: list[ActuacionDto] = []
        for doc in documentos:
            archivoId = doc.get("archivoId")
            if not doc.get("archivoIdSgd"):
                self.logger.warning(
                    f"🟡 radicado={proceso.numeroProceso} (procesoId={proceso.procesoId}) archivoId={archivoId} "
                    f"sin archivoIdSgd (no sincronizado con SGD aun) -> se omite."
                )
                continue
            try:
                imagenUrl = await self.scraper.obtenerUrlDocumento(client, idToken, proceso.procesoId, archivoId)
                autos.append(self._buildAutoItemDto(doc, imagenUrl))
                actuaciones.append(self._buildActuacionDto(proceso, doc))
            except Exception:
                self.logger.exception(
                    f"🔴 Error resolviendo archivoId={archivoId} de radicado={proceso.numeroProceso} "
                    f"(procesoId={proceso.procesoId}); se continua"
                )

        if not autos:
            self.logger.warning(
                f"🟡 radicado={proceso.numeroProceso} (procesoId={proceso.procesoId}) tenia "
                f"{len(documentos)} documento(s) pero ninguno quedo disponible para publicar."
            )
            return len(documentos), 0

        actuacionesPublicadas = await self._publishActuaciones(actuaciones)
        autosPublicados = await self._publishAutos(proceso, autos)

        self.logger.info(
            f"📊 radicado={proceso.numeroProceso} -> {actuacionesPublicadas} actuacion(es) publicada(s), "
            f"{autosPublicados}/{len(autos)} url(s) de documento publicadas"
        )

        return len(documentos), actuacionesPublicadas

