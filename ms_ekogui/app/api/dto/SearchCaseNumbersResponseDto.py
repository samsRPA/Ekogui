from typing import List

from pydantic import BaseModel


class SearchCaseNumbersResponseDto(BaseModel):
    entidadId: int
    estado: str
    extraidos: int
    lotesPublicados: int
    radicadosNoEncontrados: List[str] = []

    @classmethod
    def fromResult(cls, result: dict) -> "SearchCaseNumbersResponseDto":
        return cls(
            entidadId=result["entityId"],
            estado=result["state"],
            extraidos=result["extracted"],
            lotesPublicados=result["publishedBatches"],
            radicadosNoEncontrados=result.get("notFoundCaseNumbers", []),
        )
