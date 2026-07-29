import json
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator

from app.config.base import EnvConfig

class RabbitMQSettings(EnvConfig):
    host: str = Field(..., alias="RABBITMQ_HOST")
    port: int = Field(..., alias="RABBITMQ_PORT")
    autosQueueName: str = Field(..., alias="NOT_AUTOS_QUEUE_NAME")
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
    controlAutosRama: str = Field(..., alias="TB_CONTROL_AUTOS_RAMA")

class S3Settings(EnvConfig):
    awsSecretKey: str = Field(..., alias="S3_SECRET")
    awsAccessKey: str = Field(..., alias="S3_ACCESS_KEY")
    bucketAutos: str = Field(..., alias="S3_BUCKET_ABBY")
    prefixAutos: str = Field(..., alias="S3_PREFIX_AUTOS")

class FileSettings(EnvConfig):
    tempFolder: Path  = Field(..., alias="FOLDER")

class proxiesSettings(EnvConfig):
    proxies: List[Optional[str]] = Field(default_factory=list, alias="PROXIES")

    @field_validator("proxies", mode="before")
    @classmethod
    def parse_proxies(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

class Settings(EnvConfig):
    s3: S3Settings = S3Settings()
    file: FileSettings = FileSettings()
    proxy: proxiesSettings = proxiesSettings()
    db: DatabaseSettings = DatabaseSettings()
    rabbitmq: RabbitMQSettings = RabbitMQSettings()
    tables: tablesSettings = tablesSettings()

def loadConfig() -> Settings:
    return Settings()
