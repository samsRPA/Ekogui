import re
import asyncio
import logging
from typing import List, Optional, Union

from app.application.dto.ProcessBatchRecord import ProcessBatchRecord
from app.domain.interfaces.IBrokerProducer import IBrokerProducer
from app.domain.interfaces.IEkoguiScraper import IEkoguiScraper
from app.domain.interfaces.IEkoguiService import IEkoguiService
from app.domain.interfaces.IExcelReader import IExcelReader
from app.domain.interfaces.IHttpClient import IHttpClient

CASE_NUMBER_PATTERN = re.compile(r"[0-9]{23}")
CASE_NUMBER_SEPARATORS = re.compile(r"[\s-]")


class EkoguiService(IEkoguiService):
    def __init__(self, producer: IBrokerProducer, httpClient: IHttpClient, scraper: IEkoguiScraper,
                 excelReader: IExcelReader):
        self.producer = producer
        self.httpClient = httpClient
        self.scraper = scraper
        self.excelReader = excelReader
        self.logger = logging.getLogger(__name__)

    def _resolveEntities(self, entities: Union[str, List[int]], availableEntities: list[dict]) -> list[dict]:
        if entities == "todos":
            return availableEntities

        availableById = {e["id"]: e for e in availableEntities}
        resolved = []
        for entityId in entities:
            entity = availableById.get(entityId)
            if entity is None:
                self.logger.warning(f"🟡 entidadId={entityId} no esta entre las entidades disponibles para este usuario; se omite.")
                continue
            resolved.append(entity)
        return resolved

    async def publishOrder(self, entities: Union[str, List[int]], state: str, batchSize: int) -> dict:
        publishedBatches = 0
        extracted = 0
        entitiesWithErrors: list[int] = []
        self.logger.info(
            f"🌐 Iniciando publishOrder - entidades={entities} estado={state} batchSize={batchSize}"
        )
        try:
            async with self.httpClient.contextClient() as client:
                loggedIn = await self.scraper.login(client)
                if not loggedIn:
                    raise RuntimeError("No se pudo iniciar sesion en Ekogui")

                personId = await self.scraper.getUserPersonId(client)
                availableEntities = await self.scraper.getPersonEntities(client, personId)
                entitiesToProcess = self._resolveEntities(entities, availableEntities)

                for entity in entitiesToProcess:
                    entityId, entityName = entity["id"], entity["nombre"]

                    try:
                        processes = await self.scraper.listEntityProcesses(client, entityId, entityName, state)
                    except Exception:
                        entitiesWithErrors.append(entityId)
                        self.logger.exception(
                            f"🔴 Error listando procesos de entidadId={entityId} ({entityName}); se continua con la siguiente entidad"
                        )
                        continue

                    if not processes:
                        self.logger.warning(f"🟡 entidadId={entityId} ({entityName}) sin procesos para publicar")
                        continue

                    extracted += len(processes)
                    totalBatches = (len(processes) + batchSize - 1) // batchSize
                    for index, start in enumerate(range(0, len(processes), batchSize), start=1):
                        rawBatch = processes[start:start + batchSize]
                        try:
                            batch = ProcessBatchRecord.fromPage(rawBatch, entityId, entityName, state)
                            await self.producer.publishMessage(batch.model_dump(), priority=1)
                            publishedBatches += 1
                        except Exception:
                            self.logger.exception(
                                f"🔴 Error publicando lote {index}/{totalBatches} de entidadId={entityId} ({entityName}); "
                                f"se continua con el siguiente lote"
                            )

        except Exception as e:
            self.logger.error(f"🔴 Error en publishOrder: {e}")
            raise

        self.logger.info(
            f"🟢 publishOrder finalizado - entidades={entities} estado={state} -> "
            f"extraidos={extracted} lotesPublicados={publishedBatches} entidadesConError={entitiesWithErrors}"
        )
        return {
            "entities": entities,
            "state": state,
            "extracted": extracted,
            "publishedBatches": publishedBatches,
            "entitiesWithErrors": entitiesWithErrors,
        }

    async def searchCaseNumber(self, entityId: int, caseNumber: str, state: str) -> dict:
        self.logger.info(f"🌐 Iniciando busqueda de radicado={caseNumber} - entidadId={entityId} estado={state}")

        async with self.httpClient.contextClient() as client:
            loggedIn = await self.scraper.login(client)
            if not loggedIn:
                raise RuntimeError("No se pudo iniciar sesion en Ekogui")

            personId = await self.scraper.getUserPersonId(client)
            availableEntities = await self.scraper.getPersonEntities(client, personId)
            entitiesById = {e["id"]: e for e in availableEntities}
            entity = entitiesById.get(entityId)
            if entity is None:
                raise ValueError(f"entidadId={entityId} no esta entre las entidades disponibles para este usuario")

            entityName = entity["nombre"]
            process = await self.scraper.searchProcessByCaseNumber(client, entityId, entityName, caseNumber, state)

            if process is None:
                self.logger.warning(f"🟡 radicado={caseNumber} no encontrado - entidadId={entityId} ({entityName})")
                return {
                    "entities": [entityId],
                    "state": state,
                    "extracted": 0,
                    "publishedBatches": 0,
                    "entitiesWithErrors": [entityId],
                }

            batch = ProcessBatchRecord.fromPage([process], entityId, entityName, state)
            await self.producer.publishMessage(batch.model_dump(), priority=2)

        self.logger.info(f"🟢 radicado={caseNumber} encontrado y publicado - entidadId={entityId} ({entityName})")
        return {
            "entities": [entityId],
            "state": state,
            "extracted": 1,
            "publishedBatches": 1,
            "entitiesWithErrors": [],
        }

    async def searchCaseNumbers(self, entityId: int, caseNumbers: List[str], state: str) -> dict:
        self.logger.info(
            f"🌐 Iniciando busqueda de {len(caseNumbers)} radicados - entidadId={entityId} estado={state}"
        )

        foundProcesses: list[dict] = []
        notFoundCaseNumbers: List[str] = []

        async with self.httpClient.contextClient() as client:
            loggedIn = await self.scraper.login(client)
            if not loggedIn:
                raise RuntimeError("No se pudo iniciar sesion en Ekogui")

            personId = await self.scraper.getUserPersonId(client)
            availableEntities = await self.scraper.getPersonEntities(client, personId)
            entitiesById = {e["id"]: e for e in availableEntities}
            entity = entitiesById.get(entityId)
            if entity is None:
                raise ValueError(f"entidadId={entityId} no esta entre las entidades disponibles para este usuario")

            entityName = entity["nombre"]

            for caseNumber in caseNumbers:
                process = await self.scraper.searchProcessByCaseNumber(client, entityId, entityName, caseNumber, state)
                if process is None:
                    self.logger.warning(f"🟡 radicado={caseNumber} no encontrado - entidadId={entityId} ({entityName})")
                    notFoundCaseNumbers.append(caseNumber)
                else:
                    foundProcesses.append(process)

            publishedBatches = 0
            if foundProcesses:
                batch = ProcessBatchRecord.fromPage(foundProcesses, entityId, entityName, state)
                await self.producer.publishMessage(batch.model_dump(), priority=2)
                publishedBatches = 1

        self.logger.info(
            f"🟢 busqueda de radicados finalizada - entidadId={entityId} ({entityName}) -> "
            f"extraidos={len(foundProcesses)} radicadosNoEncontrados={notFoundCaseNumbers}"
        )
        return {
            "entityId": entityId,
            "state": state,
            "extracted": len(foundProcesses),
            "publishedBatches": publishedBatches,
            "notFoundCaseNumbers": notFoundCaseNumbers,
        }

    @staticmethod
    def _cleanCaseNumber(raw: str) -> Optional[str]:
        """Strips whitespace/dashes and returns the case number if it is
        exactly 23 digits, or None otherwise."""
        caseNumber = CASE_NUMBER_SEPARATORS.sub("", str(raw))
        return caseNumber if CASE_NUMBER_PATTERN.fullmatch(caseNumber) else None

    def _normalizeCaseNumbers(self, rawCaseNumbers: List[str]) -> tuple[list[str], list[str]]:
        """Splits the input into valid case numbers (cleaned, deduplicated,
        original order kept) and the raw values that are not 23 digits."""
        valid: list[str] = []
        invalid: list[str] = []
        seen: set[str] = set()
        for raw in rawCaseNumbers:
            caseNumber = self._cleanCaseNumber(raw)
            if caseNumber is None:
                invalid.append(str(raw))
            elif caseNumber not in seen:
                seen.add(caseNumber)
                valid.append(caseNumber)
        return valid, invalid

    async def searchCaseNumbersBulk(self, entityId: int, caseNumbers: List[str], state: str, batchSize: int) -> dict:
        """Bulk search shared by the JSON and Excel endpoints: one login, one
        walk over the entity's paginated listing filtered locally (instead of
        one request per case number), and the matches are published in
        batches of batchSize so several bot replicas can share the work."""
        valid, invalid = self._normalizeCaseNumbers(caseNumbers)
        self.logger.info(
            f"🌐 Iniciando busqueda masiva - entidadId={entityId} estado={state} validos={len(valid)} invalidos={len(invalid)} batchSize={batchSize}"
        )

        result = {
            "entityId": entityId,
            "state": state,
            "searched": len(valid),
            "found": 0,
            "publishedBatches": 0,
            "notFound": [],
            "invalid": invalid,
        }
        if not valid:
            self.logger.warning(f"🟡 entidadId={entityId} sin radicados validos para buscar")
            return result

        async with self.httpClient.contextClient() as client:
            loggedIn = await self.scraper.login(client)
            if not loggedIn:
                raise RuntimeError("No se pudo iniciar sesion en Ekogui")

            personId = await self.scraper.getUserPersonId(client)
            availableEntities = await self.scraper.getPersonEntities(client, personId)
            entity = {e["id"]: e for e in availableEntities}.get(entityId)
            if entity is None:
                raise ValueError(f"entidadId={entityId} no esta entre las entidades disponibles para este usuario")

            entityName = entity["nombre"]
            processes = await self.scraper.searchProcessesByCaseNumbers(client, entityId, entityName, set(valid), state)

        publishedBatches = 0
        totalBatches = (len(processes) + batchSize - 1) // batchSize
        for index, start in enumerate(range(0, len(processes), batchSize), start=1):
            rawBatch = processes[start:start + batchSize]
            try:
                batch = ProcessBatchRecord.fromPage(rawBatch, entityId, entityName, state)
                await self.producer.publishMessage(batch.model_dump(), priority=2)
                publishedBatches += 1
            except Exception:
                self.logger.exception(
                    f"🔴 Error publicando lote {index}/{totalBatches} de entidadId={entityId} ({entityName}); "
                    f"se continua con el siguiente lote"
                )

        foundCaseNumbers = {str(p.get("numeroProceso") or "").strip() for p in processes}
        notFound = [caseNumber for caseNumber in valid if caseNumber not in foundCaseNumbers]

        self.logger.info(
            f"🟢 Busqueda masiva finalizada - entidadId={entityId} ({entityName}) -> "
            f"encontrados={len(processes)} lotesPublicados={publishedBatches}/{totalBatches} noEncontrados={len(notFound)} invalidos={len(invalid)}"
        )
        result.update(found=len(processes), publishedBatches=publishedBatches, notFound=notFound)
        return result

    async def searchCaseNumbersFromExcel(self, entityId: int, content: bytes, state: str, batchSize: int) -> dict:
        """Reads the first column of the first sheet and runs the same bulk
        search. The first value is treated as a header and skipped when it is
        not a case number, so files with or without header both work."""
        values = await asyncio.to_thread(self.excelReader.readFirstColumn, content)
        if values and self._cleanCaseNumber(values[0]) is None:
            self.logger.info(f"📄 Se omite el encabezado '{values[0]}'")
            values = values[1:]

        self.logger.info(f"📄 Excel leido - {len(values)} valores en la primera columna")
        return await self.searchCaseNumbersBulk(entityId, values, state, batchSize)
