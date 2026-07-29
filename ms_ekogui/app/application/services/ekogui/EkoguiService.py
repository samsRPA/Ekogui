import logging
from typing import List, Union

from app.application.dto.LoteProcesosRecord import LoteProcesosRecord
from app.domain.interfaces.IBrokerProducer import IBrokerProducer
from app.domain.interfaces.IEkoguiScraper import IEkoguiScraper
from app.domain.interfaces.IEkoguiService import IEkoguiService
from app.domain.interfaces.IHttpClient import IHttpClient


class EkoguiService(IEkoguiService):
    def __init__(self, producer: IBrokerProducer, httpClient: IHttpClient, scraper: IEkoguiScraper):
        self.producer = producer
        self.httpClient = httpClient
        self.scraper = scraper
        self.logger = logging.getLogger(__name__)

    def _resolverEntidades(self, entidades: Union[str, List[int]], entidadesDisponibles: list[dict]) -> list[dict]:
        if entidades == "todos":
            return entidadesDisponibles

        disponiblesPorId = {e["id"]: e for e in entidadesDisponibles}
        resueltas = []
        for entidadId in entidades:
            entidad = disponiblesPorId.get(entidadId)
            if entidad is None:
                self.logger.warning(f"🟡 entidadId={entidadId} no esta entre las entidades disponibles para este usuario; se omite.")
                continue
            resueltas.append(entidad)
        return resueltas

    async def publishOrder(self, entidades: Union[str, List[int]], estado: str, batchSize: int) -> dict:
        lotesPublicados = 0
        extraidos = 0
        entidadesConError: list[int] = []
        self.logger.info(
            f"🌐 Iniciando publishOrder - entidades={entidades} estado={estado} batchSize={batchSize}"
        )
        try:
            async with self.httpClient.contextClient() as client:
                loggedIn = await self.scraper.login(client)
                if not loggedIn:
                    raise RuntimeError("No se pudo iniciar sesion en Ekogui")

                personaId = await self.scraper.buscarPersonaUsuario(client)
                entidadesDisponibles = await self.scraper.obtenerEntidadesPersona(client, personaId)
                entidadesARecorrer = self._resolverEntidades(entidades, entidadesDisponibles)

                for entidad in entidadesARecorrer:
                    entidadId, entidadNombre = entidad["id"], entidad["nombre"]

                    try:
                        procesos = await self.scraper.listarProcesosDeEntidad(client, entidadId, entidadNombre, estado)
                    except Exception:
                        entidadesConError.append(entidadId)
                        self.logger.exception(
                            f"🔴 Error listando procesos de entidadId={entidadId} ({entidadNombre}); se continua con la siguiente entidad"
                        )
                        continue

                    if not procesos:
                        self.logger.warning(f"🟡 entidadId={entidadId} ({entidadNombre}) sin procesos para publicar")
                        continue

                    extraidos += len(procesos)
                    totalLotes = (len(procesos) + batchSize - 1) // batchSize
                    for indice, inicio in enumerate(range(0, len(procesos), batchSize), start=1):
                        lotecrudo = procesos[inicio:inicio + batchSize]
                        try:
                            lote = LoteProcesosRecord.fromPagina(lotecrudo, entidadId, entidadNombre, estado)
                            await self.producer.publishMessage(lote.model_dump(), priority=2)
                            lotesPublicados += 1
                        except Exception:
                            self.logger.exception(
                                f"🔴 Error publicando lote {indice}/{totalLotes} de entidadId={entidadId} ({entidadNombre}); "
                                f"se continua con el siguiente lote"
                            )

        except Exception as e:
            self.logger.error(f"🔴 Error en publishOrder: {e}")
            raise

        self.logger.info(
            f"🟢 publishOrder finalizado - entidades={entidades} estado={estado} -> "
            f"extraidos={extraidos} lotesPublicados={lotesPublicados} entidadesConError={entidadesConError}"
        )
        return {
            "entidades": entidades,
            "estado": estado,
            "extraidos": extraidos,
            "lotesPublicados": lotesPublicados,
            "entidadesConError": entidadesConError,
        }

    async def searchCaseNumber(self, entidadId: int, radicado: str, estado: str) -> dict:
        self.logger.info(f"🌐 Iniciando busqueda de radicado={radicado} - entidadId={entidadId} estado={estado}")

        async with self.httpClient.contextClient() as client:
            loggedIn = await self.scraper.login(client)
            if not loggedIn:
                raise RuntimeError("No se pudo iniciar sesion en Ekogui")

            personaId = await self.scraper.buscarPersonaUsuario(client)
            entidadesDisponibles = await self.scraper.obtenerEntidadesPersona(client, personaId)
            entidadesPorId = {e["id"]: e for e in entidadesDisponibles}
            entidad = entidadesPorId.get(entidadId)
            if entidad is None:
                raise ValueError(f"entidadId={entidadId} no esta entre las entidades disponibles para este usuario")

            entidadNombre = entidad["nombre"]
            proceso = await self.scraper.buscarProcesoPorRadicado(client, entidadId, entidadNombre, radicado, estado)

            if proceso is None:
                self.logger.warning(f"🟡 radicado={radicado} no encontrado - entidadId={entidadId} ({entidadNombre})")
                return {
                    "entidades": [entidadId],
                    "estado": estado,
                    "extraidos": 0,
                    "lotesPublicados": 0,
                    "entidadesConError": [entidadId],
                }

            lote = LoteProcesosRecord.fromPagina([proceso], entidadId, entidadNombre, estado)
            await self.producer.publishMessage(lote.model_dump(), priority=2)

        self.logger.info(f"🟢 radicado={radicado} encontrado y publicado - entidadId={entidadId} ({entidadNombre})")
        return {
            "entidades": [entidadId],
            "estado": estado,
            "extraidos": 1,
            "lotesPublicados": 1,
            "entidadesConError": [],
        }
