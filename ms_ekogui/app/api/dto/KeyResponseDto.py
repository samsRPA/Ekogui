from typing import List, Union

from pydantic import BaseModel


class KeyResponseDto(BaseModel):
    entidades: Union[str, List[int]]
    estado: str
    extraidos: int
    lotesPublicados: int
    entidadesConError: List[int] = []

    @classmethod
    def fromResultado(cls, resultado: dict) -> "KeyResponseDto":
        return cls(
            entidades=resultado["entidades"],
            estado=resultado["estado"],
            extraidos=resultado["extraidos"],
            lotesPublicados=resultado["lotesPublicados"],
            entidadesConError=resultado.get("entidadesConError", []),
        )
