from abc import ABC, abstractmethod

from app.domain.interfaces.IContextClient import IContextClient


class IEkoguiScraper(ABC):
    """Scraper de Ekogui para el consumidor: recibe un lote de procesos de
    UNA entidad (ya resuelta por el productor) y abre una sola sesion
    (login + SSO + seleccion de entidad) para recorrerlos todos."""

    @abstractmethod
    async def iniciarSesionEntidad(self, client: IContextClient, entidadId: int) -> str:
        """Login completo (SP Angular -> WSO2 IS -> vuelta al SP) + SSO al
        modulo judicial (/ekoguims) + seleccion de la entidad. Retorna el
        idToken (JWT) a usar como Authorization: Bearer en el resto de
        llamadas de esta misma sesion para esa entidad."""
        ...

    @abstractmethod
    async def listarActuacionesProceso(self, client: IContextClient, idToken: str,
                                        procesoEntidadId: int) -> list[dict]:
        """Retorna la evolucion procesal (lista de actuaciones) del proceso."""
        ...

    @abstractmethod
    async def listarDocumentosProceso(self, client: IContextClient, idToken: str,
                                       procesoId: int) -> list[dict]:
        """Retorna los documentos de soporte del proceso (cada uno con
        'archivoId', 'archivoIdSgd', 'tipoAnexoDescripcion', 'extension')."""
        ...

    @abstractmethod
    async def obtenerUrlDocumento(self, client: IContextClient, idToken: str,
                                   procesoId: int, archivoId: int) -> str:
        """Retorna la URL 'imagen?g=<hash>' del documento. A diferencia de la
        URL final 'temporales/<archivo>.pdf' (que el SGD genera al vuelo y
        expira), esta URL con hash es estable y se puede publicar en la cola
        de 'autos' para que el consumidor la descargue directamente."""
        ...
