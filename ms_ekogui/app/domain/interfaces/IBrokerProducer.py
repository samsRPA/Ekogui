from abc import ABC, abstractmethod

class IBrokerProducer(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establece la conexión con el broker."""
        ...

    @abstractmethod
    async def publishMessage(self, message: dict, priority: int | None = None) -> None:
        """Publica un mensaje en la cola con prioridad opcional."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Cierra la conexión con el broker."""
        ...
