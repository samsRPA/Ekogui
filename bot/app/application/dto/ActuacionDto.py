import re
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, field_serializer, field_validator


class ActuacionDto(BaseModel):
    """Registro de actuacion (destino RAMA), listo para publicar en
    COLL_QUEUE_NAME. El collector lo inserta tal cual via CARGUE_MASIVO
    (ver bot/app/application/services/ScraperService.py:_buildActuacionRecord
    y collector/app/infrastructure/database/repositories/ActRepo.py)."""

    RADICADO_RAMA:      Optional[str] = None
    COD_DESPACHO_RAMA:  Optional[str] = None
    FECHA_ACTUACION:    Optional[date] = None
    ACTUACION_RAMA:     Optional[str] = None
    ANOTACION_RAMA:     str = "INFORMACION DESCARGADA EKOGUI"
    ORIGEN_DATOS:       str = "EKOGUI"

    @field_validator("RADICADO_RAMA", mode="before")
    @classmethod
    def _normalizeRadicado(cls, value):
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

    @field_validator("FECHA_ACTUACION", mode="before")
    @classmethod
    def _parseFechaActuacion(cls, value):
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

    @field_serializer("FECHA_ACTUACION")
    def _serializarFechaActuacion(self, value: Optional[date]) -> Optional[str]:
        """El collector espera la fecha en formato 'DD-MM-YYYY'."""
        return value.strftime("%d-%m-%Y") if value else None
