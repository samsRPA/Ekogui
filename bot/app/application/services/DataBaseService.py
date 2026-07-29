import logging
from datetime import date

from app.domain.interfaces.IDataBaseService import IDataBaseService
from app.infrastructure.database.repositories.ActRama import ActRama
from app.infrastructure.database.repositories.CAutoRamaRep import CAutoRamaRep


class DataBaseService(IDataBaseService):

    def __init__(self, acRamaRep: ActRama, cAutoRamaRep: CAutoRamaRep):
        self.acRamaRep = acRamaRep
        self.cAutoRamaRep = cAutoRamaRep
        self.logger = logging.getLogger(__name__)

    async def actuacionExiste(self, conn, radicado: str, fecha: date, actuacion: str, anotacion: str) -> bool:
        """Recibe una conexion ya adquirida por el llamador (no abre ni
        cierra conexiones aqui) y delega en el repositorio. Si la
        comprobacion falla (BD caida, timeout, etc.) no se descarta el
        registro: se retorna False para que igual se publique hacia el
        collector, que vuelve a validar existencia antes de insertar."""
        try:
            return await self.acRamaRep.checkActExist(conn, radicado, fecha, actuacion, anotacion)
        except Exception:
            self.logger.exception(
                f"🔴 Error comprobando existencia de actuacion radicado={radicado}; se publica de todas formas"
            )
            return False

    async def autoExiste(self, conn, radicado: str, fecha: date, urlAuto: str) -> bool:
        """Recibe una conexion ya adquirida por el llamador (no abre ni
        cierra conexiones aqui) y delega en el repositorio. Si la
        comprobacion falla (BD caida, timeout, etc.) no se descarta el
        registro: se retorna False para que igual se publique hacia
        downloader_autos, que vuelve a validar existencia antes de
        descargar/insertar."""
        try:
            return await self.cAutoRamaRep.checkAutoExist(conn, fecha, radicado, urlAuto, "EKOGUI")
        except Exception:
            self.logger.exception(
                f"🔴 Error comprobando existencia de auto radicado={radicado}; se publica de todas formas"
            )
            return False
