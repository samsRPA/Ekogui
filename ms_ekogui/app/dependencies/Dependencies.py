from dependency_injector import containers, providers

from app.domain.interfaces.IBrokerProducer import IBrokerProducer
from app.domain.interfaces.IEkoguiScraper import IEkoguiScraper
from app.domain.interfaces.IEkoguiService import IEkoguiService
from app.domain.interfaces.IHttpClient import IHttpClient

from app.config.config import Settings
from app.infrastructure.http.httpClient import AioHttpClient
from app.infrastructure.rabbitmq.RabbitMQProducer import RabbitMQProducer
from app.application.services.ekogui.EkoguiScraper import EkoguiScraper
from app.application.services.ekogui.EkoguiService import EkoguiService


class Dependencies(containers.DeclarativeContainer):
    config = providers.Configuration()
    settings: providers.Singleton[Settings] = providers.Singleton(Settings)
    wiring_config = containers.WiringConfiguration(
        modules=["app.api.routes.EkoguiRoutes"]
    )

    # Provider del cliente HTTP (sesion persistente + clientes temporales)
    httpClient: providers.Singleton[IHttpClient] = providers.Singleton(
        AioHttpClient,
        sslIntermediateCertPath=settings.provided.http.sslIntermediateCertPath,
    )

    # Provider del scraper (login + listado paginado de procesos)
    ekoguiScraper: providers.Factory[IEkoguiScraper] = providers.Factory(
        EkoguiScraper,
        documentType=settings.provided.ekoguiCredentials.documentType,
        documentNumber=settings.provided.ekoguiCredentials.documentNumber,
        password=settings.provided.ekoguiCredentials.password,
    )

    # Provider del productor (publica hacia la cola del scraper/consumidor)
    rabbitmqProducer: providers.Singleton[IBrokerProducer] = providers.Singleton(
        RabbitMQProducer,
        host=settings.provided.rabbitmq.host,
        port=settings.provided.rabbitmq.port,
        queueName=settings.provided.rabbitmq.queueScrapeName,
        login=settings.provided.rabbitmq.user,
        password=settings.provided.rabbitmq.password,
        maxPriority=2,
    )

    # Factory del servicio principal
    ekoguiService: providers.Factory[IEkoguiService] = providers.Factory(
        EkoguiService,
        producer=rabbitmqProducer,
        httpClient=httpClient,
        scraper=ekoguiScraper,
    )
