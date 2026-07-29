import json
import logging

import aio_pika

from aiormq.exceptions import (
    AMQPConnectionError, ChannelClosed, ConnectionClosed,
    PublishError, AuthenticationError, AMQPError
)

from app.domain.interfaces.IBrokerProducer import IBrokerProducer

class RabbitMQProducer(IBrokerProducer):
    def __init__(self, host:str, port:int, queueName:str, login: str, password: str, maxPriority: int | None = None) -> None:
        self.host = host
        self.port = port
        self.login = login
        self.channel = None
        self.connection = None
        self.password = password
        self.queueName = queueName
        self.maxPriority = maxPriority
        self.logger = logging.getLogger(__name__)

    async def connect(self) -> None:
        try:
            self.connection = await aio_pika.connect_robust(
                host = self.host,
                port = self.port,
                login = self.login,
                password = self.password,
                timeout = 15
            )
            self.channel = await self.connection.channel()
            arguments = {"x-max-priority": self.maxPriority} if self.maxPriority else {}
            await self.channel.declare_queue(
                self.queueName,
                durable = True,
                arguments = arguments
            )
            self.logger.info("🔵 Conectado a RabbitMQ - Producer")

        except AuthenticationError:
            self.logger.error("🔴 Error de autenticación con RabbitMQ")
            raise

        except AMQPConnectionError as e:
            self.logger.error(f"🔴 No se pudo conectar al broker: {e}")
            raise

        except AMQPError as e:
            self.logger.error(f"🔴 Error general de AMQP durante connect(): {e}")
            raise

        except Exception as e:
            self.logger.error(f"🔴 Error inesperado: {e}")
            raise

    async def publishMessage(self, message: dict, priority: int | None = None) -> None:
        try:
            body = json.dumps(
                message,
                ensure_ascii = False,
                default=str
            ).encode("utf-8")

            msg = aio_pika.Message(
                body = body,
                priority = priority,
                content_type = "application/json",
                content_encoding = "utf-8",
                delivery_mode = aio_pika.DeliveryMode.NOT_PERSISTENT
            )

            await self.channel.default_exchange.publish(
                msg,
                routing_key = self.queueName,
            )

        except PublishError as e:
            self.logger.error(f"🔴 Error publicando mensaje (PublishError): {e}")
            raise

        except ChannelClosed:
            self.logger.error("🔴 El canal está cerrado, no se pudo publicar.")
            raise

        except ConnectionClosed:
            self.logger.error("🔴 La conexión se cerró mientras se publicaba.")
            raise

        except AMQPError as e:
            self.logger.error(f"🔴 Error AMQP publicando mensaje: {e}")
            raise

        except Exception as e:
            self.logger.exception(f"🔴 Error inesperado enviando mensaje: {e}")
            raise

    async def close(self) -> None:
        if self.connection:
            await self.connection.close()
            self.logger.info("🔌 Conexión con RabbitMQ cerrada")
