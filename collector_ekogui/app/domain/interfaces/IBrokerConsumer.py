from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Any

class IBrokerConsumer(ABC):

    @abstractmethod
    async def connect(self) -> None:
        """Establece la conexión con el broker."""
        ...

    @abstractmethod
    async def callback(self, message: Any) -> None:
        """Procesa un mensaje entrante del broker."""
        ...

    @abstractmethod
    async def startConsuming(self) -> None:
        """Inicia el consumo de mensajes de la cola."""
        ...
