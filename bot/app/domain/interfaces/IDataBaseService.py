from abc import ABC, abstractmethod
from datetime import date


class IDataBaseService(ABC):

    @abstractmethod
    async def actuacionExiste(self, conn, radicado: str, fecha: date, actuacion: str, anotacion: str) -> bool:
        """Comprueba si la actuacion ya existe en RAMA, usando una conexion
        ya adquirida por el llamador. Si falla la comprobacion (BD no
        disponible, timeout, etc.), no debe descartar el registro: debe
        retornar False para que igual se publique hacia el collector, que
        vuelve a validar existencia antes de insertar."""
        ...

    @abstractmethod
    async def autoExiste(self, conn, radicado: str, fecha: date, urlAuto: str) -> bool:
        """Comprueba si el auto (por su URL) ya existe en RAMA, usando una
        conexion ya adquirida por el llamador. Si falla la comprobacion (BD
        no disponible, timeout, etc.), no debe descartar el registro: debe
        retornar False para que igual se publique hacia downloader_autos,
        que vuelve a validar existencia antes de descargar/insertar."""
        ...

