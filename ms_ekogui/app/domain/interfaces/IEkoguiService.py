from abc import ABC, abstractmethod
from typing import List, Union


class IEkoguiService(ABC):
    @abstractmethod
    async def publishOrder(
        self,
        entities: Union[str, List[int]],
        state: str,
        batchSize: int,
    ) -> dict:
        pass

    @abstractmethod
    async def searchCaseNumber(
        self,
        entityId: int,
        caseNumber: str,
        state: str,
    ) -> dict:
        pass

    @abstractmethod
    async def searchCaseNumbers(
        self,
        entityId: int,
        caseNumbers: List[str],
        state: str,
    ) -> dict:
        pass

    @abstractmethod
    async def searchCaseNumbersBulk(
        self,
        entityId: int,
        caseNumbers: List[str],
        state: str,
        batchSize: int,
    ) -> dict:
        pass

    @abstractmethod
    async def searchCaseNumbersFromExcel(
        self,
        entityId: int,
        content: bytes,
        state: str,
        batchSize: int,
    ) -> dict:
        pass
