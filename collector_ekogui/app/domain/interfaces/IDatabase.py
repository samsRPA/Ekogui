from abc import ABC, abstractmethod

class IDatabase(ABC):
    @property
    @abstractmethod
    def isConnected(self) -> bool:
        """Indica si la base de datos está conectada."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Establece la conexión con la base de datos."""
        ...

    @abstractmethod
    async def acquireConnection(self):
        """Adquiere una conexión del pool."""
        ...

    @abstractmethod
    async def releaseConnection(self, conn):
        """Libera una conexión de vuelta al pool."""
        ...

    @abstractmethod
    async def commit(self, conn):
        """Confirma la transacción activa en la conexión."""
        ...

    @abstractmethod
    async def closeConnection(self):
        """Cierra el pool de conexiones."""
        ...