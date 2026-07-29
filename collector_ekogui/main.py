import signal
import logging
import asyncio

from app.config.config import loadConfig
from app.dependencies.Dependencies import Dependencies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

def setupSignalHandlers(stopEvent: asyncio.Event):
    """Configura manejadores de señales para parar el loop limpiamente."""
    loop = asyncio.get_running_loop()

    def handleSignal():
        stopEvent.set()

    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, handleSignal)


async def run():
    """Ejecuta el servicio principal con manejo de señal y cierre ordenado."""
    consumerTask = None
    config = loadConfig()
    dependency = Dependencies()
    dependency.settings.override(config)
    
    # Dependencias principales
    db = dependency.db()
    consumer = dependency.consumer()
    collector = dependency.collectorService()
    
    stopEvent = asyncio.Event()
    setupSignalHandlers(stopEvent)

    try:
        await db.connect()
        collector.start()
        
        # Arrancar el consumer
        consumerTask = asyncio.create_task(
            consumer.startConsuming()
        )        
        await stopEvent.wait()

    except asyncio.CancelledError:
        logging.info("🔴 Cancelado por evento externo.")
    except Exception:
        logging.exception("🔴 Error durante la ejecución principal")

    finally:
        if consumerTask:
            consumerTask.cancel()
            try:
                await consumerTask
            except asyncio.CancelledError:
                logging.info("📴 Consumer detenido correctamente.")

        await collector.stop()

        try:
            if db.isConnected:
                await db.closeConnection()
                logging.info("🔌 Conexión a Oracle cerrada correctamente.")
        except Exception as e:
            logging.warning(f"🔴 Error al cerrar conexión a la base de datos: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.info("👋 Interrupción manual detectada (CTRL+C).")
