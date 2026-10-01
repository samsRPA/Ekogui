from typing import List

from pydantic import BaseModel, Field


class SearchCaseNumbersBulkResponseDto(BaseModel):
    entityId: int
    state: str
    searched: int = Field(description="Valid, unique case numbers searched.")
    found: int = Field(description="Processes found and sent to the queue.")
    publishedBatches: int
    notFound: List[str] = Field(default=[], description="Valid case numbers that did not show up in the entity listing.")
    invalid: List[str] = Field(default=[], description="Received values that are not 23-digit case numbers.")

    @classmethod
    def fromResult(cls, result: dict) -> "SearchCaseNumbersBulkResponseDto":
        return cls(
            entityId=result["entityId"],
            state=result["state"],
            searched=result["searched"],
            found=result["found"],
            publishedBatches=result["publishedBatches"],
            notFound=result.get("notFound", []),
            invalid=result.get("invalid", []),
        )
