import json
import logging
import asyncio

from app.domain.interfaces import IDatabase
from app.infrastructure.database.repositories.ActRepo import ActRepo
from app.domain.interfaces.ICollectorService import ICollectorService

class CollectorService(ICollectorService):
    def __init__(self, db: IDatabase, actRepo: ActRepo, batchSize: int, flushInterval: int) -> None:
        self.db = db
        self.actRepo = actRepo
        self.batchSize = batchSize
        self.flushInterval = flushInterval

        self._buffer = []
        self._task = None
        self._lock = asyncio.Lock()  # Evita race conditions
        self._resetEvent = asyncio.Event()   # Reinicia el temporizador
        self._stopEvent = asyncio.Event()    # Detiene el loop de forma segura

    async def _flush(self) -> None:
        """Inserta el batch actual y reinicia el temporizador de forma segura."""
        # 🔒 Bloque crítico: copiar y limpiar buffer atómicamente
        async with self._lock:
            if not self._buffer:
                return

            batch = self._buffer.copy()
            self._buffer.clear()

        conn = None
        try:
            conn = await self.db.acquireConnection()
            mensaje = await self.actRepo.insertBatch(conn, batch)
            logging.info(f"🟢 Batch insertado correctamente: {mensaje} | size={len(batch)}")

            # (Opcional) si realmente necesitas throttling
            await asyncio.sleep(3)

        except Exception as e:
            logging.error(f"🔴 Error insertando batch: {e}")

            # En caso de fallo, reinsertar los datos al buffer (opcional pero recomendado)
            async with self._lock:
                self._buffer = batch + self._buffer

        finally:
            if conn:
                await self.db.releaseConnection(conn)

            # Reinicia el temporizador
            self._resetEvent.set()

    async def _autoFlush(self) -> None:
        """Flush automático por tiempo."""
        try:
            while not self._stopEvent.is_set():
                try:
                    await asyncio.wait_for(
                        self._resetEvent.wait(),
                        timeout=self.flushInterval
                    )
                    self._resetEvent.clear()

                except asyncio.TimeoutError:
                    async with self._lock:
                        bufferSize = len(self._buffer)

                    if bufferSize > 0:
                        logging.info(
                            f"⏱️ Flush automático | {self.flushInterval}s | batch = {bufferSize}"
                        )
                        await self._flush()

                    self._resetEvent.clear()

        except asyncio.CancelledError:
            logging.info("⚠️ Tarea de auto-flush cancelada.")

        finally:
            # Flush final al apagar
            async with self._lock:
                has_data = bool(self._buffer)

            if has_data:
                logging.info("💾 Flush final antes de apagar...")
                await self._flush()

    async def _uploadData(self, payload: dict) -> None:
        """Agrega datos al buffer de forma segura."""
        try:
            async with self._lock:
                self._buffer.append(payload)
                bufferSize = len(self._buffer)

            if bufferSize >= self.batchSize:
                logging.info(
                    f"🚀 Batch alcanzó tamaño máximo ({self.batchSize}), ejecutando flush manual."
                )
                await self._flush()

        except Exception as e:
            logging.exception("🔴 Error agregando datos al buffer")
            raise
    
    def start(self) -> None:
        if not self._task:
            self._stopEvent.clear()
            self._task = asyncio.create_task(self._autoFlush())
            logging.info("🔵 Se inicia flush automático por tiempo.")

    async def stop(self) -> None:
        if self._task:
            self._stopEvent.set()
            self._resetEvent.set()  # Despierta el loop si está dormido
            await self._task
            self._task = None
            logging.info("🔌 Flush automático detenido.")

    async def handleMessage(self, body: bytes) -> None:
        try:
            # Decodificar bytes → string
            payload = json.loads(body.decode("utf-8"))

            # Enviar al buffer
            await self._uploadData(payload = payload)

        except json.JSONDecodeError as e:
            logging.error(f"🔴 Error decodificando JSON: {e} | body={body!r}")

        except Exception as e:
            logging.exception(f"🔴 Error manejando mensaje: {e}")
            raise
