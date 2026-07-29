from typing import Optional

from pydantic import BaseModel


class ProcesoRecord(BaseModel):
    procesoId: int
    procesoEntidadId: Optional[int] = None
    numeroProceso: str
    despachoInicialNombre: Optional[str] = None
    entidadId: int
    entidadNombre: str

    @classmethod
    def fromRaw(cls, raw: dict, entidadId: int, entidadNombre: str) -> "ProcesoRecord":
        if not raw or raw.get("id") is None:
            raise ValueError("Registro de proceso vacío o inválido.")
        return cls(
            procesoId=raw["id"],
            procesoEntidadId=raw.get("idProcesoEntidad"),
            numeroProceso=str(raw.get("numeroProceso") or raw["id"]),
            despachoInicialNombre=raw.get("despachoInicialNombre"),
            entidadId=entidadId,
            entidadNombre=entidadNombre,
        )
