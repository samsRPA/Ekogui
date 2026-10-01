from typing import List, Union

from pydantic import BaseModel


class KeyResponseDto(BaseModel):
    entidades: Union[str, List[int]]
    estado: str
    extraidos: int
    lotesPublicados: int
    entidadesConError: List[int] = []

    @classmethod
    def fromResult(cls, result: dict) -> "KeyResponseDto":
        return cls(
            entidades=result["entities"],
            estado=result["state"],
            extraidos=result["extracted"],
            lotesPublicados=result["publishedBatches"],
            entidadesConError=result.get("entitiesWithErrors", []),
        )
