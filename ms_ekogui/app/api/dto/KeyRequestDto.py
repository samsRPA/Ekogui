from typing import List, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

Estado = Literal["PROCESO_ENTIDAD_ACTIVO", "PROCESO_ENTIDAD_TERMINADO"]


class KeyRequestDto(BaseModel):
    entidades: Union[Literal["todos"], List[int]] = Field(description="'todos', o una lista de entidadId a procesar.")
    estado: Estado = Field(default="PROCESO_ENTIDAD_ACTIVO", description="Estado de los procesos a buscar.")
    batchSize: int = Field(default=10, ge=1, description="Cantidad de procesos por lote publicado en la cola.")

    model_config = ConfigDict(extra="forbid")

    @field_validator("entidades")
    @classmethod
    def validarEntidades(cls, v):
        if v == "todos":
            return v
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("Si no usas 'todos', envía una lista con al menos un entidadId")
        for item in v:
            if not isinstance(item, int) or item <= 0:
                raise ValueError("Cada entidadId debe ser un entero positivo")
        return v
