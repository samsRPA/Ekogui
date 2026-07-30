from dependency_injector import containers, providers

from app.domain.interfaces.IBrokerConsumer import IBrokerConsumer
from app.domain.interfaces.IDatabase import IDatabase
from app.domain.interfaces.IS3Manager import IS3Manager
from app.domain.interfaces.IHttpClient import IHttpClient
from app.domain.interfaces.IAutosDownloaderService import IAutosDownloaderService

from app.config.config import Settings

from app.application.services.AutosDownloaderService import AutosDownloaderService

from app.infrastructure.s3.S3Manager import S3Manager
from app.infrastructure.database.OracleDB import OracleDB
from app.infrastructure.http.httpClient import AioHttpClient
from app.infrastructure.filesystem.TempWorkspace import TempWorkspace
from app.infrastructure.rabbitmq.RabbitMQConsumer import RabbitMQConsumer
from app.infrastructure.database.repositories.CAutoRamaRep import CAutoRamaRep
from app.application.factories.ProcessorFactory import ProcessorFactory
from app.domain.interfaces.IFileProcessor import IFileProcessor
from app.domain.interfaces.IProcessorFactory import IProcessorFactory
from app.infrastructure.downloaders.DocxProcessor import DocxProcessor
from app.infrastructure.downloaders.ImageProcessor import ImageProcessor
from app.infrastructure.downloaders.PdfProcessor import PdfProcessor
from app.infrastructure.downloaders.XlsxProcessor import XlsxProcessor
from app.infrastructure.downloaders.HtmlXlsProcessor import HtmlXlsProcessor
from app.infrastructure.downloaders.CompressedProcessor import CompressedProcessor


class Dependencies(containers.DeclarativeContainer):
    config = providers.Configuration()
    settings: providers.Singleton[Settings] = providers.Singleton(Settings)
    wiring_config = containers.WiringConfiguration(
        modules=["main"]
    )

    # Provider de db
    db: providers.Singleton[IDatabase] = providers.Singleton(
        OracleDB,
        user=settings.provided.db.user,
        password=settings.provided.db.password,
        host=settings.provided.db.host,
        port=settings.provided.db.port,
        dbName=settings.provided.db.dbName,
        pooled=settings.provided.db.pooled,
        poolClass="SIUGJ_NFT_DOWNLOADER_AUTOS",
    )

    # Repositories
    cAutoRamaRep: providers.Factory = providers.Factory(
        CAutoRamaRep,
        table=settings.provided.tables.controlAutosRama,
    )

    # Filesystem
    tempWorkspace = providers.Singleton(
        TempWorkspace,
        basePath=settings.provided.file.tempFolder,
    )

    # Cliente HTTP
    httpClient: providers.Singleton[IHttpClient] = providers.Singleton(
        AioHttpClient,
        maxConnections=20,
        proxies=settings.provided.proxy.proxies,
    )

    # S3 - bucket de autos
    s3Manager: providers.Singleton[IS3Manager] = providers.Singleton(
        S3Manager,
        awsAccessKey=settings.provided.s3.awsAccessKey,
        awsSecretKey=settings.provided.s3.awsSecretKey,
        bucketNft=settings.provided.s3.bucketAutos,
        prefixNft=settings.provided.s3.prefixAutos,
    )

    # Provider de procesadores: descargan y convierten a PDF sin tocar el
    # contenido original.
    pdfProcessor: providers.Factory[IFileProcessor] = providers.Factory(PdfProcessor)
    docxProcessor: providers.Factory[IFileProcessor] = providers.Factory(DocxProcessor)
    imageProcessor: providers.Factory[IFileProcessor] = providers.Factory(ImageProcessor)
    xlsxProcessor: providers.Factory[IFileProcessor] = providers.Factory(XlsxProcessor)
    htmlXlsProcessor: providers.Factory[IFileProcessor] = providers.Factory(HtmlXlsProcessor)

    # CompressedProcessor necesita la propia ProcessorFactory para poder
    # resolver cada archivo que trae adentro (incluyendo un comprimido
    # dentro de otro). Como processorFactory a su vez necesita apuntar a
    # compressedProcessor en su mapa, se crea primero sin esa dependencia y
    # se completa con add_kwargs() una vez que processorFactory ya existe
    # -> unica forma de romper el ciclo en la definicion del contenedor.
    compressedProcessor: providers.Factory[IFileProcessor] = providers.Factory(CompressedProcessor)

    # ProcessorFactory con mapa inyectado
    processorFactory: providers.Factory[IProcessorFactory] = providers.Factory(
        ProcessorFactory,
        processorMap={
            "application/pdf": pdfProcessor,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": docxProcessor,
            "application/msword": docxProcessor,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": xlsxProcessor,
            "application/vnd.ms-excel": xlsxProcessor,
            "image/png": imageProcessor,
            "image/jpeg": imageProcessor,
            "image/jpg": imageProcessor,
            "image/webp": imageProcessor,
            "image/gif": imageProcessor,
            "image/bmp": imageProcessor,
            "image/tiff": imageProcessor,
            "htmlXsl": htmlXlsProcessor,
            "application/zip": compressedProcessor,
            "application/x-7z-compressed": compressedProcessor,
            "application/x-rar-compressed": compressedProcessor,
        }
    )
    compressedProcessor.add_kwargs(processorFactory=processorFactory)

    # Servicio principal
    autosDownloaderService: providers.Factory[IAutosDownloaderService] = providers.Factory(
        AutosDownloaderService,
        httpClient=httpClient,
        tempWorkspace=tempWorkspace,
        db=db,
        s3Manager=s3Manager,
        cAutoRamaRep=cAutoRamaRep,
        processorFactory=processorFactory,
    )

    # Consumidor RabbitMQ
    consumer: providers.Singleton[IBrokerConsumer] = providers.Singleton(
        RabbitMQConsumer,
        host=settings.provided.rabbitmq.host,
        port=settings.provided.rabbitmq.port,
        queueName=settings.provided.rabbitmq.autosQueueName,
        prefetchCount=settings.provided.rabbitmq.prefetchCount,
        login=settings.provided.rabbitmq.user,
        password=settings.provided.rabbitmq.password,
        handler=autosDownloaderService.provided.handleMessage,
    )
