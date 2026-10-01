from typing import List

from pydantic import BaseModel

from app.application.dto.ProcessRecord import ProcessRecord


class ProcessBatchRecord(BaseModel):
    """Un mensaje = una pagina completa de procesos de una entidad. El
    consumidor abre UNA sola sesion/login y recorre todos los 'procesos' del
    lote en esa misma sesion, en vez de loguearse por cada proceso."""
    entidadId: int
    entidadNombre: str
    estado: str
    procesos: List[ProcessRecord]

    @classmethod
    def fromPage(cls, rawProcesses: list[dict], entityId: int, entityName: str, state: str) -> "ProcessBatchRecord":
        return cls(
            entidadId=entityId,
            entidadNombre=entityName,
            estado=state,
            procesos=[ProcessRecord.fromRaw(raw, entityId, entityName) for raw in rawProcesses],
        )
