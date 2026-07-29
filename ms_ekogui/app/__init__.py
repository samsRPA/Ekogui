import logging

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.views import getApiRouter
from app.config.config import loadConfig
from app.dependencies.Dependencies import Dependencies

logging.basicConfig(
    level = logging.INFO,
    format = '%(asctime)s - %(levelname)s - %(message)s',
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = loadConfig()
    dependency = Dependencies()
    dependency.settings.override(config)

    app.container = dependency

    httpClient = dependency.httpClient()
    producer = dependency.rabbitmqProducer()
    try:
        await producer.connect()
        await httpClient.init()
        yield  # Aquí se ejecuta la app
    except Exception as e:
        logging.exception("🔴 Error durante la ejecución principal", exc_info=e)
    finally:
        try:
            await producer.close()
        except Exception as e:
            logging.warning(f"🟡 No se pudo cerrar RabbitMQ correctamente: {e}")
        try:
            await httpClient.close()
        except Exception as e:
            logging.warning(f"🟡 No se pudo cerrar el cliente http correctamente: {e}")

app = FastAPI(
    lifespan=lifespan,
    title="ms_ekogui API Service",
    description=(
        "ms_ekogui app"
    ),
    version="1.0.0",
    contact={
        "name": "Rpa Litigando Department",
        "email": "samuel.monsalve@litigando.com",
    },
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/swagger",
    redoc_url="/api/v1/redocs",
)

app.include_router(getApiRouter())

@app.get("/")
def default():
    return {"mensaje": "Hello ekogui"}
