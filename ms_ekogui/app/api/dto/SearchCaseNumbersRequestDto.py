from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.dto.KeyRequestDto import Estado


class SearchCaseNumbersRequestDto(BaseModel):
    entidadId: int = Field(description="Id de la entidad donde buscar los radicados.")
    radicados: List[str] = Field(description="Lista de numeros de proceso (radicados) a buscar.")
    estado: Estado = Field(default="PROCESO_ENTIDAD_ACTIVO", description="Estado de los procesos a buscar.")

    model_config = ConfigDict(extra="forbid")

    @field_validator("radicados")
    @classmethod
    def validarRadicados(cls, v):
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("Envía una lista con al menos un radicado")
        return v
