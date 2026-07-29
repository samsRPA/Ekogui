import signal
import logging
import asyncio

from app.config.config import loadConfig
from app.dependencies.Dependencies import Dependencies


logging.basicConfig(
    level=logging.INFO,
     format=f'%(asctime)s - %(levelname)s - [%(module)s] - %(message)s',
)

logger = logging.getLogger(__name__)

def setupSignalHandlers(stopEvent: asyncio.Event):
    loop = asyncio.get_running_loop()

    def handleSignal():
        stopEvent.set()

    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, handleSignal)

async def run():
    consumerTask = None
    config = loadConfig()
    dependency = Dependencies()
    dependency.settings.override(config)

    db = dependency.db()
    consumer = dependency.consumer()
    httpClient = dependency.httpClient()

    stopEvent = asyncio.Event()
    setupSignalHandlers(stopEvent)

    try:
        await db.connect()
        await httpClient.init()

        # Arrancar el consumer
        consumerTask = asyncio.create_task(
            consumer.startConsuming()
        )

        await stopEvent.wait()
    except Exception as e:
        logger.exception(f"🔴 Error durante la ejecución principal {e}")
    finally:
        await httpClient.close()

        if consumerTask:
            consumerTask.cancel()

        try:
            if db.isConnected:
                await db.closeConnection()
            logger.info("🔌 Todos los recursos cerrados correctamente.")
        except Exception as e:
            logger.warning(f"🔴 Error al cerrar recursos: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("👋 Señal de interrupción detectada (CTRL+C o kill).")
