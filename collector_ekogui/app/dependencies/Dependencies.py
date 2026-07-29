from dependency_injector import containers, providers

from app.domain.interfaces import IBrokerConsumer
from app.domain.interfaces.IDatabase import IDatabase
from app.domain.interfaces.ICollectorService import ICollectorService

from app.config.config import Settings

from app.infrastructure.database.OracleDB import OracleDB
from app.infrastructure.database.repositories.ActRepo import ActRepo
from app.application.services.CollectorService import CollectorService
from app.infrastructure.rabbitmq.RabbitMQConsumer import RabbitMQConsumer

class Dependencies(containers.DeclarativeContainer):
    config = providers.Configuration()
    settings: providers.Singleton[Settings] = providers.Singleton(Settings)
    wiring_config = containers.WiringConfiguration(
        modules=["main"]
    )
    
    #Provider de db
    db: providers.Singleton[IDatabase] = providers.Singleton(
        OracleDB,
        user = settings.provided.db.user,
        password = settings.provided.db.password,
        host = settings.provided.db.host,
        port = settings.provided.db.port,
        dbName = settings.provided.db.dbName,
        pooled = settings.provided.db.pooled,
        poolClass = "EKOGUI_ACT_COLL",
    )
    
    #Repositories
    actRepo: providers.Factory = providers.Factory(
        ActRepo,
        tipoCargue = settings.provided.coll.tipoCargue,
    )
    
    # Provider de servicio
    collectorService:providers.Singleton[ICollectorService] = providers.Singleton(
        CollectorService,
        db = db,
        actRepo = actRepo,
        batchSize = settings.provided.coll.batchSize,
        flushInterval = settings.provided.coll.flushInterval
    )

    # Provider del consumidor
    consumer: providers.Singleton[IBrokerConsumer] = providers.Singleton(
        RabbitMQConsumer,
        host = settings.provided.rabbitmq.host,
        port = settings.provided.rabbitmq.port,
        queueName = settings.provided.rabbitmq.queueColl,
        prefetchCount = settings.provided.rabbitmq.prefetchCount,
        login = settings.provided.rabbitmq.user,
        password = settings.provided.rabbitmq.password,
        handler = collectorService.provided.handleMessage,
    )
