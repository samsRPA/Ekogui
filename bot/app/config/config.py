import json
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator

from app.config.base import EnvConfig

class RabbitMQSettings(EnvConfig):
    host: str = Field(..., alias="RABBITMQ_HOST")
    port: int = Field(..., alias="RABBITMQ_PORT")
    queueScrapeName: str = Field(..., alias="QUEUE_SCRAPE_NAME")
    # Cola de salida (autos/actuaciones extraidas), sin usar por ahora pero
    # se deja declarada para cuando se reactive ese productor.
    autosQueueName: str = Field(..., alias="AUTOS_QUEUE_NAME")
    # Cola de salida hacia el collector (actuaciones RAMA para CARGUE_MASIVO).
    collQueueName: str = Field(..., alias="COLL_QUEUE_NAME")
    prefetchCount: int = Field(..., alias="PREFETCH_COUNT")
    user: str = Field(..., alias="RABBIT_USER")
    password: str = Field(..., alias="RABBIT_PASSWORD")

class DatabaseSettings(EnvConfig):
    user: str = Field(..., alias="DB_USERNAME")
    password: str = Field(..., alias="DB_PASSWORD")
    host: str = Field(..., alias="DB_HOST")
    port: str = Field(..., alias="DB_PORT")
    dbName: str = Field(..., alias="DB_NAME")
    pooled: bool = Field(False, alias="DB_POOLED")

class tablesSettings(EnvConfig):
    actuacionesRama: str = Field(..., alias="TB_ACTUACIONES_RAMA")
    controlAutosRama: str = Field(..., alias="TB_CONTROL_AUTOS_RAMA")



class EkoguiCredentialsSettings(EnvConfig):
    documentType: str = Field(..., alias="EKOGUI_DOCUMENT_TYPE")
    documentNumber: str = Field(..., alias="EKOGUI_DOCUMENT_NUMBER")
    password: str = Field(..., alias="EKOGUI_PASSWORD")

class HttpSettings(EnvConfig):
    sslIntermediateCertPath: str = Field(..., alias="SSL_INTERMEDIATE_CERT_PATH")

class proxiesSettings(EnvConfig):
    proxies: List[Optional[str]] = Field(default_factory=list, alias="PROXIES")

    @field_validator("proxies", mode="before")
    @classmethod
    def parse_proxies(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

class Settings(EnvConfig):

    proxy: proxiesSettings = proxiesSettings()
    db: DatabaseSettings = DatabaseSettings()
    rabbitmq: RabbitMQSettings = RabbitMQSettings()
    tables: tablesSettings = tablesSettings()
    ekoguiCredentials: EkoguiCredentialsSettings = EkoguiCredentialsSettings()
    http: HttpSettings = HttpSettings()

def loadConfig() -> Settings:
    return Settings()
