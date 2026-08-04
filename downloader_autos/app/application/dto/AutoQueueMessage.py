import uuid
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, model_validator


class AutoItem(BaseModel):
    """Un auto/documento individual dentro del lote de un radicado."""

    fechaAuto:    date
    urlAuto:      str
    namePDF:      str 
    urlAutoName:  Optional[str] = None

    @model_validator(mode="after")
    def _fallbackUrlAutoName(self):
        # Mensajes viejos en cola (o de una replica de bot sin actualizar)
        # pueden no traer urlAutoName; sin este respaldo el f-string en
        # AutosDownloaderService lo convierte en el string literal "None".
        # urlAutoName nunca debe quedar vacio/None: si falta, se reconstruye
        # a partir de urlAuto (que es obligatorio) y namePDF si esta.
        if not self.urlAutoName:
            self.urlAutoName = f"{self.urlAuto}#{self.namePDF}" if self.namePDF else self.urlAuto
        return self


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
