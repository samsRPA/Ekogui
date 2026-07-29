import logging
import asyncio
from typing import Callable, Awaitable

import aio_pika
from aio_pika.exceptions import (
    AMQPConnectionError,
    ChannelClosed,
    MessageProcessError,
)
from aiormq.exceptions import ChannelInvalidStateError
from app.domain.interfaces.IBrokerConsumer import IBrokerConsumer

class RabbitMQConsumer(IBrokerConsumer):
    def __init__(self, host: str, port: int, queueName: str, prefetchCount: int, login: str, password: str, handler: Callable[[bytes], Awaitable[None]], timeout: int = 10) -> None:
        self.host = host
        self.port = port
        self.login = login
        self.password = password
        self.queue = None
        self.channel = None
        self.timeout = timeout
        self.connection = None
        self._handler = handler
        self.queueName = queueName
        self.prefetchCount = prefetchCount
    
    async def connect(self) -> None:
        try:
            self.connection = await aio_pika.connect_robust(
                host = self.host,
                port = self.port,
                login = self.login,
                password = self.password,
                timeout = self.timeout
            )
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count = self.prefetchCount)
            self.queue = await self.channel.declare_queue(
                self.queueName,
                durable = True
            )
            logging.info("🔵 Conectado a RabbitMQ - Consumer")

        except (AMQPConnectionError, ChannelClosed) as e:
            logging.error(f"🔴 Error crítico conectando al broker: {e}")
            raise

        except Exception as e:
            logging.error(f"🔴 Error inesperado conectando al consumer: {e}")
            raise
    
    async def callback(self, message: aio_pika.IncomingMessage) -> None:
        try:
            async with message.process(ignore_processed=True):
                try:
                    await self._handler(message.body)

                except MessageProcessError:
                    logging.warning("🟡 Intento de NACK/ACK inválido.")

                except Exception as e:
                    logging.error(f"🔴 Error procesando mensaje: {e}")
                    try:
                        await message.nack(requeue=False)
                    except MessageProcessError:
                        logging.warning("🟡 Mensaje ya estaba procesado.")

        except ChannelInvalidStateError:
            # Canal cerrado mientras se procesaba el mensaje (ej: DB caída canceló el task).
            # RabbitMQ reencola el mensaje automáticamente al cerrar el canal.
            logging.warning("🟡 Canal RabbitMQ cerrado durante procesamiento — mensaje será reencolado.")
    
    async def startConsuming(self) -> None:
        if not self.channel or not self.queue:
            await self.connect()

        try:
            await self.queue.consume(self.callback)
            logging.info("🎧 Esperando mensajes...")

            while True:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logging.info("👋 Consumo cancelado por el usuario.")

        except AMQPConnectionError as e:
            logging.error(f"🔴 Conexión con RabbitMQ perdida: {e}")

        except ChannelClosed as e:
            logging.error(f"🔴 El canal fue cerrado inesperadamente: {e}")

        except Exception as e:
            logging.error(f"🔴 Error inesperado en el consumo: {e}")
            raise

        finally:
            if self.channel:
                await self.channel.close()
                logging.info("🔌 Canal RabbitMQ cerrado.")

            if self.connection:
                await self.connection.close()
                logging.info("🔌 Conexión RabbitMQ cerrada.")
                