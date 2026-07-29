from abc import ABC, abstractmethod
from typing import List, Union


class IEkoguiService(ABC):
    @abstractmethod
    async def publishOrder(
        self,
        entidades: Union[str, List[int]],
        estado: str,
        batchSize: int,
    ) -> dict:
        pass

    @abstractmethod
    async def searchCaseNumber(
        self,
        entidadId: int,
        radicado: str,
        estado: str,
    ) -> dict:
        pass
