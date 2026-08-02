from abc import ABC, abstractmethod

from app.domain.interfaces.IContextClient import IContextClient


class SesionExpiradaError(RuntimeError):
    """El gateway respondio 403 a una llamada autenticada de /ekoguims: el
    idToken de la sesion (obtenido una sola vez por lote en
    iniciarSesionEntidad) expiro a mitad de un lote largo. El llamador puede
    refrescar la sesion con iniciarSesionEntidad() y reintentar."""

    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.status = status


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
                                   procesoId: int, archivoId: int,
                                   maxRetries: int = 3, backoffSeconds: float = 2.0) -> str:
        """Retorna la URL 'imagen?g=<hash>' del documento. A diferencia de la
        URL final 'temporales/<archivo>.pdf' (que el SGD genera al vuelo y
        expira), esta URL con hash es estable y se puede publicar en la cola
        de 'autos' para que el consumidor la descargue directamente.
        Reintenta con backoff si el gateway Zuul responde con un 500
        transitorio (SHORTCIRCUIT/GENERAL). Lanza una excepcion si tras los
        reintentos no se obtuvo una URL http(s) valida -> el llamador debe
        omitir ese documento sin publicarlo."""
        ...
