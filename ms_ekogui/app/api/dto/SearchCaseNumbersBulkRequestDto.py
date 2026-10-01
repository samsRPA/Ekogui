from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.dto.KeyRequestDto import State


class SearchCaseNumbersBulkRequestDto(BaseModel):
    entityId: int = Field(description="Id of the entity to search the case numbers in.")
    caseNumbers: List[str] = Field(description="Case numbers (23 digits) to search for.")
    state: State = Field(default="PROCESO_ENTIDAD_ACTIVO", description="State of the processes to search.")
    batchSize: int = Field(default=10, ge=1, description="Number of processes per batch published to the queue.")

    model_config = ConfigDict(extra="forbid")

    @field_validator("caseNumbers")
    @classmethod
    def validateCaseNumbers(cls, v):
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("Send a list with at least one case number")
        return v
