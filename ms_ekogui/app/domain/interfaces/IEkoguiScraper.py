from abc import ABC, abstractmethod
from typing import Optional

from app.domain.interfaces.IContextClient import IContextClient


class IEkoguiScraper(ABC):
    """Etapa de listado del scraper de Ekogui: login completo y consulta
    paginada de procesos judiciales por entidad. La descarga de documentos
    por proceso vive en el consumidor (fuera de este productor)."""

    @abstractmethod
    async def login(self, client: IContextClient) -> bool:
        """Ejecuta el login completo (SP Angular -> WSO2 IS -> vuelta al SP).
        Retorna True si al final quedamos con la sesion logueada."""
        ...

    @abstractmethod
    async def getUserPersonId(self, client: IContextClient) -> int:
        """Retorna el personId del usuario logueado."""
        ...

    @abstractmethod
    async def getPersonEntities(self, client: IContextClient, personId: int) -> list[dict]:
        """Retorna las entidades (id, nombre) a las que el usuario tiene acceso."""
        ...

    @abstractmethod
    async def listEntityProcesses(self, client: IContextClient, entityId: int,
                                  entityName: str, state: str) -> list[dict]:
        """Retorna TODOS los procesos judiciales de la entidad en una sola
        consulta (sin paginar contra Ekogui). Internamente maneja el SSO al
        modulo judicial y la seleccion de entidad (una sola vez por
        entityId, cacheado) sin exponer esos detalles al llamador."""
        ...

    @abstractmethod
    async def searchProcessByCaseNumber(self, client: IContextClient, entityId: int,
                                        entityName: str, caseNumber: str,
                                        state: str) -> Optional[dict]:
        """Busca UN proceso puntual por su numeroProceso (radicado) dentro de
        la entidad. Retorna el proceso si lo encuentra, o None."""
        ...

    @abstractmethod
    async def searchProcessesByCaseNumbers(self, client: IContextClient, entityId: int,
                                           entityName: str, caseNumbers: set[str],
                                           state: str) -> list[dict]:
        """Bulk lookup of case numbers inside the entity by walking the
        paginated listing and filtering locally (not one request per case
        number). Returns only the matching processes."""
        ...
