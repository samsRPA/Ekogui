from abc import ABC, abstractmethod

class IAutosDownloaderService(ABC):
    @abstractmethod
    async def handleMessage(self, body: bytes) -> None:
        """Procesa un mensaje de la cola de autos: descarga, sube a S3 e inserta el registro de control."""
        ...
