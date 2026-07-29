
from typing import List, Optional

from pydantic import BaseModel


class ProcesoItem(BaseModel):
    procesoId: int
    procesoEntidadId: Optional[int] = None
    numeroProceso: str
    despachoInicialNombre: Optional[str] = None
    entidadId: int
    entidadNombre: str


class EkoguiReq(BaseModel):
    """Mensaje publicado por ms_ekogui: un lote (una pagina) de procesos de
    UNA sola entidad. El consumidor abre una sola sesion (login + seleccion
    de entidad) y recorre todos los 'procesos' del lote en esa misma
    sesion."""

    entidadId: int
    entidadNombre: str
    estado: str
    procesos: List[ProcesoItem]

    @classmethod
    def fromRaw(cls, rawBody: dict) -> "EkoguiReq":
        return cls(**rawBody)
