import uuid
from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class AutoItem(BaseModel):
    """Un auto/documento individual dentro del lote de un radicado."""

    fechaAuto: date
    urlAuto:   str


class AutoQueueMessage(BaseModel):
    """Lote de autos de UN radicado, publicado por bot en AUTOS_QUEUE_NAME
    (un mensaje por radicado, no por documento ni por notificacion; ver
    AutoDto/ScraperService._processProceso en bot)."""

    radicacion: str
    despacho:   Optional[str] = None
    origen:     str = "EKOGUI"
    autos:      List[AutoItem]

    @classmethod
    def fromRaw(cls, rawBody: dict) -> "AutoQueueMessage":
        return cls(**rawBody)

    @property
    def folderName(self) -> str:
        return f"{self.radicacion}_{uuid.uuid4().hex}"
