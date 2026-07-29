from pydantic import Field

from app.config.base import EnvConfig
from pydantic_settings import BaseSettings

class RabbitMQSettings(EnvConfig):
    host: str = Field(..., alias="RABBITMQ_HOST")
    port: int = Field(..., alias="RABBITMQ_PORT")
    queueScrapeName: str = Field(..., alias="QUEUE_SCRAPE_NAME")
    user: str = Field(..., alias="RABBIT_USER")
    password: str = Field(..., alias="RABBIT_PASSWORD")

class EkoguiCredentialsSettings(EnvConfig):
    documentType: str = Field(..., alias="EKOGUI_DOCUMENT_TYPE")
    documentNumber: str = Field(..., alias="EKOGUI_DOCUMENT_NUMBER")
    password: str = Field(..., alias="EKOGUI_PASSWORD")

class HttpSettings(EnvConfig):
    sslIntermediateCertPath: str = Field(..., alias="SSL_INTERMEDIATE_CERT_PATH")

class Settings(BaseSettings):
    rabbitmq: RabbitMQSettings = RabbitMQSettings()
    ekoguiCredentials: EkoguiCredentialsSettings = EkoguiCredentialsSettings()
    http: HttpSettings = HttpSettings()


def loadConfig() -> Settings:
    return Settings()
