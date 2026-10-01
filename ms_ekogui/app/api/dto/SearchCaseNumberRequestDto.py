from pydantic import BaseModel, ConfigDict, Field

from app.api.dto.KeyRequestDto import State


class SearchCaseNumberRequestDto(BaseModel):
    entidadId: int = Field(description="Id de la entidad donde buscar el radicado.")
    radicado: str = Field(description="Numero de proceso (radicado) a buscar.")
    estado: State = Field(default="PROCESO_ENTIDAD_ACTIVO", description="Estado del proceso a buscar.")

    model_config = ConfigDict(extra="forbid")
