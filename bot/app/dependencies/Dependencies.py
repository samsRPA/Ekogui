from dependency_injector import containers, providers

from app.domain.interfaces import IBrokerConsumer
from app.domain.interfaces.IBrokerProducer import IBrokerProducer
from app.domain.interfaces.IEkoguiScraper import IEkoguiScraper
from app.domain.interfaces.IDatabase import IDatabase

from app.domain.interfaces.IHttpClient import IHttpClient


from app.domain.interfaces.IScraperService import IScraperService
from app.domain.interfaces.IDataBaseService import IDataBaseService

from app.config.config import Settings
from app.application.services.ekogui.EkoguiScraper import EkoguiScraper
from app.application.services.ScraperService import ScraperService
from app.application.services.DataBaseService import DataBaseService


from app.infrastructure.database.OracleDB import OracleDB
from app.infrastructure.http.httpClient import AioHttpClient

from app.infrastructure.rabbitmq.RabbitMQConsumer import RabbitMQConsumer
from app.infrastructure.rabbitmq.RabbitMQProducer import RabbitMQProducer
from app.infrastructure.database.repositories.ActRama import ActRama
from app.infrastructure.database.repositories.CAutoRamaRep import CAutoRamaRep


class Dependencies(containers.DeclarativeContainer):
    config = providers.Configuration()
    settings: providers.Singleton[Settings] = providers.Singleton(Settings)
    wiring_config = containers.WiringConfiguration(
        modules=["main"]
    )

    # Provider de db - usado por ScraperService para validar existencia de
    # actuaciones en RAMA justo antes de publicarlas (ver _publishActuaciones).
    db: providers.Singleton[IDatabase] = providers.Singleton(
        OracleDB,
        user=settings.provided.db.user,
        password=settings.provided.db.password,
        host=settings.provided.db.host,
        port=settings.provided.db.port,
        dbName=settings.provided.db.dbName,
        pooled=settings.provided.db.pooled,
        poolClass="EKOGUI_ACT_BOT",
    )

    # Repositories

    acRamaRep:providers.Factory = providers.Factory(
        ActRama,
        table = settings.provided.tables.actuacionesRama,
    )

    cAutoRamaRep:providers.Factory = providers.Factory(
        CAutoRamaRep,
        table = settings.provided.tables.controlAutosRama,
    )

    # Cliente HTTP
    httpClient: providers.Singleton[IHttpClient] = providers.Singleton(
        AioHttpClient,
        sslIntermediateCertPath=settings.provided.http.sslIntermediateCertPath,
        maxConnections=20,
        proxies=settings.provided.proxy.proxies,
    )


    # Servicios de datos
    dataBaseService: providers.Factory[IDataBaseService] = providers.Factory(
        DataBaseService,
        acRamaRep=acRamaRep,
        cAutoRamaRep=cAutoRamaRep,
    )


    # Scraper de Ekogui: recibe el lote de una entidad, abre una sola sesion
    # (login + SSO + seleccion de entidad) y extrae actuaciones + documentos.
    scraper: providers.Factory[IEkoguiScraper] = providers.Factory(
        EkoguiScraper,
        documentType=settings.provided.ekoguiCredentials.documentType,
        documentNumber=settings.provided.ekoguiCredentials.documentNumber,
        password=settings.provided.ekoguiCredentials.password,
    )

    # Productor RabbitMQ - publica actuaciones/autos extraidos (sin usar por
    # ahora, declarado para cuando se retome ese flujo).
    autosProducer: providers.Singleton[IBrokerProducer] = providers.Singleton(
        RabbitMQProducer,
        host=settings.provided.rabbitmq.host,
        port=settings.provided.rabbitmq.port,
        queueName=settings.provided.rabbitmq.autosQueueName,
        login=settings.provided.rabbitmq.user,
        password=settings.provided.rabbitmq.password,
        maxPriority=2,
    )

    # Productor RabbitMQ - publica las actuaciones (registros RAMA) hacia el
    # collector, que las inserta via CARGUE_MASIVO.
    collProducer: providers.Singleton[IBrokerProducer] = providers.Singleton(
        RabbitMQProducer,
        host=settings.provided.rabbitmq.host,
        port=settings.provided.rabbitmq.port,
        queueName=settings.provided.rabbitmq.collQueueName,
        login=settings.provided.rabbitmq.user,
        password=settings.provided.rabbitmq.password,
    )

    # Servicio principal
    scraperService: providers.Factory[IScraperService] = providers.Factory(
        ScraperService,
        scraper=scraper,
        httpClient=httpClient,
        db=db,
        dataBaseService=dataBaseService,
        producer=autosProducer,
        collProducer=collProducer,
    )

    # Consumidor RabbitMQ - escucha la cola donde ms_ekogui publica los lotes
    consumer: providers.Singleton[IBrokerConsumer] = providers.Singleton(
        RabbitMQConsumer,
        host=settings.provided.rabbitmq.host,
        port=settings.provided.rabbitmq.port,
        queueName=settings.provided.rabbitmq.queueScrapeName,
        prefetchCount=settings.provided.rabbitmq.prefetchCount,
        login=settings.provided.rabbitmq.user,
        password=settings.provided.rabbitmq.password,
        handler=scraperService.provided.handleMessage,
    )
