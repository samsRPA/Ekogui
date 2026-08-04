import re
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, field_validator, model_validator


class AutoItemDto(BaseModel):
    """Un auto/documento individual dentro del lote de un radicado."""

    fechaAuto:  date
    urlAuto:         str 
    namePDF:         str 
    urlAutoName:     Optional[str] = None

    @model_validator(mode="after")
    def _buildUrlAutoName(self):
        self.urlAutoName = f"{self.urlAuto}#{self.namePDF}"
        return self

    @field_validator("fechaAuto", mode="before")
    @classmethod
    def _parseFechaAuto(cls, value):
        """Acepta fechas ISO con hora (ej. '2026-07-27T14:22:00.25Z') y las
        deja solo como date. Python < 3.11 solo acepta fracciones de segundo
        de 3 o 6 digitos, asi que se rellena con ceros a la derecha (Ekogui
        a veces manda 2 digitos, ej. '.41')."""
        if value is None or isinstance(value, date):
            return value
        s = str(value).strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        s = re.sub(r"\.(\d+)(?=[+-]\d{2}:\d{2}$)", lambda m: "." + m.group(1).ljust(6, "0")[:6], s)
        return datetime.fromisoformat(s).date()


class AutoDto(BaseModel):
    """Lote de autos/documentos de UN radicado, listo para publicar en
    AUTOS_QUEUE_NAME (un mensaje por radicado, no por documento). En el
    flujo de Ekogui se arma directamente desde los datos del proceso/
    documento (no se extrae de texto del PDF, a diferencia del flujo viejo
    de siugj)."""

    radicacion:      Optional[str] = None
    despacho:        Optional[str] = None
    origen:          str = "EKOGUI"
    autos:           List[AutoItemDto] = []

    @field_validator("radicacion", mode="before")
    @classmethod
    def _normalizeRadicacion(cls, value):
        """Deja el radicado solo en digitos (sin guiones/puntos/espacios).
        Si supera 23, se recorta para evitar ORA-12899."""
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        digits = re.sub(r"\D", "", s)
        if not digits:
            return None
        return digits[:23]
