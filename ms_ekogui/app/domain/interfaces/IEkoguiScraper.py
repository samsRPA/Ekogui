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
    async def buscarPersonaUsuario(self, client: IContextClient) -> int:
        """Retorna el personaId del usuario logueado."""
        ...

    @abstractmethod
    async def obtenerEntidadesPersona(self, client: IContextClient, personaId: int) -> list[dict]:
        """Retorna las entidades (id, nombre) a las que el usuario tiene acceso."""
        ...

    @abstractmethod
    async def listarProcesosDeEntidad(self, client: IContextClient, entidadId: int,
                                       entidadNombre: str, estado: str) -> list[dict]:
        """Retorna TODOS los procesos judiciales de la entidad en una sola
        consulta (sin paginar contra Ekogui). Internamente maneja el SSO al
        modulo judicial y la seleccion de entidad (una sola vez por
        entidadId, cacheado) sin exponer esos detalles al llamador."""
        ...

    @abstractmethod
    async def buscarProcesoPorRadicado(self, client: IContextClient, entidadId: int,
                                        entidadNombre: str, radicado: str,
                                        estado: str) -> Optional[dict]:
        """Busca UN proceso puntual por su numeroProceso (radicado) dentro de
        la entidad. Retorna el proceso si lo encuentra, o None."""
        ...
