from typing import List

from pydantic import BaseModel


class SearchCaseNumbersResponseDto(BaseModel):
    entidadId: int
    estado: str
    extraidos: int
    lotesPublicados: int
    radicadosNoEncontrados: List[str] = []

    @classmethod
    def fromResultado(cls, resultado: dict) -> "SearchCaseNumbersResponseDto":
        return cls(
            entidadId=resultado["entidadId"],
            estado=resultado["estado"],
            extraidos=resultado["extraidos"],
            lotesPublicados=resultado["lotesPublicados"],
            radicadosNoEncontrados=resultado.get("radicadosNoEncontrados", []),
        )
