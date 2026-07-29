from abc import ABC, abstractmethod

class ICollectorService(ABC):
    @abstractmethod
    def start(self) -> None:
        """Inicia el proceso de auto-flush en segundo plano."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Detiene el auto-flush y realiza el flush final."""
        ...
    
    @abstractmethod
    async def handleMessage(self, body: bytes):
        """Callback que recibe el mensaje crudo desde RabbitMQ."""
        ...