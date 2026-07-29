from pydantic import Field

from app.config.base import EnvConfig

class RabbitMQSettings(EnvConfig):
    host: str = Field(..., alias="RABBITMQ_HOST")
    port: int = Field(..., alias="RABBITMQ_PORT")
    queueColl: str = Field(..., alias="QUEUE_COLL_NAME")
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

class CollectorSettings(EnvConfig):
    batchSize: int = Field(..., alias="BATCH_SIZE")
    flushInterval: int = Field(..., alias="FLUSH_INTERVAL")
    tipoCargue: str = Field(..., alias="TIPO_CARGUE")

class Settings(EnvConfig):
    rabbitmq: RabbitMQSettings = RabbitMQSettings()
    db: DatabaseSettings = DatabaseSettings()
    coll: CollectorSettings = CollectorSettings()

def loadConfig() -> Settings:
    return Settings()