from pathlib import Path
from abc import ABC, abstractmethod

class IS3Manager(ABC):
    @abstractmethod
    async def uploadFile(self, filePath: Path) -> bool:
        """Sube un archivo al bucket de notificaciones y retorna si la subida fue exitosa."""
        ...
