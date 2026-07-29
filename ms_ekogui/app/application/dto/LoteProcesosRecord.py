from typing import List

from pydantic import BaseModel

from app.application.dto.ProcesoRecord import ProcesoRecord


class LoteProcesosRecord(BaseModel):
    """Un mensaje = una pagina completa de procesos de una entidad. El
    consumidor abre UNA sola sesion/login y recorre todos los 'procesos' del
    lote en esa misma sesion, en vez de loguearse por cada proceso."""
    entidadId: int
    entidadNombre: str
    estado: str
    procesos: List[ProcesoRecord]

    @classmethod
    def fromPagina(cls, rawProcesos: list[dict], entidadId: int, entidadNombre: str, estado: str) -> "LoteProcesosRecord":
        return cls(
            entidadId=entidadId,
            entidadNombre=entidadNombre,
            estado=estado,
            procesos=[ProcesoRecord.fromRaw(raw, entidadId, entidadNombre) for raw in rawProcesos],
        )
