from abc import ABC, abstractmethod
from typing import List


class IExcelReader(ABC):
    @abstractmethod
    def readFirstColumn(self, content: bytes) -> List[str]:
        """Returns, as text, the non-empty values of the first column of the
        first sheet of an .xlsx file. Headers are not interpreted here; that
        is up to the caller."""
        ...
