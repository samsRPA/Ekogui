
<div align="left">

# Ekogui

**Scraper distribuido de procesos judiciales (Ekogui — Rama Judicial / Defensa Jurídica del Estado)**

---

## Tabla de Contenidos

- [Descripción General](#descripción-general)
- [Arquitectura](#arquitectura)
- [Servicios](#servicios)
  - [ms\_ekogui](#ms_ekogui)
  - [bot](#bot)
  - [collector\_ekogui](#collector_ekogui)
  - [downloader\_autos](#downloader_autos)
- [Tipos de Archivo Soportados en downloader_autos](#tipos-de-archivo-soportados-en-downloader_autos)
- [Nomenclatura de Archivos](#nomenclatura-de-archivos)
- [Configuración del Entorno](#configuración-del-entorno)
  - [ms\_ekogui `.env`](#ms_ekogui-env)
  - [bot `.env`](#bot-env)
  - [collector\_ekogui `.env`](#collector_ekogui-env)
  - [downloader\_autos `.env`](#downloader_autos-env)
- [Despliegue](#despliegue)
- [API Reference](#api-reference)
- [Resiliencia](#resiliencia)
- [Escalado Horizontal](#escalado-horizontal)
- [Autor](#autor)

---

## Descripción General

`Ekogui` es un sistema de scraping distribuido que consulta el portal **Ekogui** de la Rama Judicial, extrae las **actuaciones** (evolución procesal) y los **documentos de soporte** de cada proceso, y descarga los **autos** (anexos) referenciados en esos documentos — convirtiéndolos a PDF sin alterar su contenido, sin importar el formato original (Word, Excel, imagen, HTML o incluso comprimidos con varios archivos adentro).

El sistema está compuesto por **un microservicio API** y **tres bots worker**, cada uno un contenedor Docker independiente, comunicados entre sí mediante **RabbitMQ**. Aplica principios **SOLID** (interfaces en `domain/interfaces`, inyección de dependencias con `dependency-injector`) y los bots admiten escalado horizontal por réplicas.

```mermaid
flowchart TD
    Cliente(["Cliente / Cron"]) -->|HTTP REST| MS["ms_ekogui\nFastAPI :8000"]
    Portal[["Portal Ekogui\nRama Judicial"]]

    MS -->|QUEUE_SCRAPE_NAME| Bot["bot\nLogin + actuaciones + documentos"]
    Bot -.->|lista procesos / documentos| Portal

    Bot -->|COLL_QUEUE_NAME\nActuacionDto| Collector["collector_ekogui\nBatch -> CARGUE_MASIVO"]
    Bot -->|AUTOS_QUEUE_NAME\nAutoDto| Downloader["downloader_autos\nDescarga + convierte a PDF"]

    Collector -->|INSERT batch| Oracle[("Oracle DB")]
    Downloader -.->|descarga documento| Portal
    Downloader -->|PDF| S3[("AWS S3")]
    Downloader -->|INSERT| Oracle

    classDef store fill:#F80000,color:#fff,stroke:#a30000;
    classDef bucket fill:#232F3E,color:#fff,stroke:#0f151d;
    class Oracle store;
    class S3 bucket;
```

---

## Arquitectura

```mermaid
flowchart LR
    Cliente(["Cliente HTTP"])

    subgraph Net["Docker Network · ekogui_net"]
        direction TB
        MS["ms_ekogui\n:8000"]
        Bot["bot\n× N réplicas"]
        Collector["collector_ekogui"]
        Downloader["downloader_autos\n× N réplicas"]
        MQ{{"RabbitMQ\n(externo)"}}

        MS -->|QUEUE_SCRAPE_NAME| Bot
        Bot -->|COLL_QUEUE_NAME| Collector
        Bot -->|AUTOS_QUEUE_NAME| Downloader
        MS -.-> MQ
        Bot -.-> MQ
        Collector -.-> MQ
        Downloader -.-> MQ
    end

    Cliente --> MS
    Downloader --> S3[("AWS S3 Bucket")]
    Collector --> Oracle[("Oracle DB\n(via tunel SSH)")]
    Downloader --> Oracle
    Bot --> Oracle

    classDef store fill:#F80000,color:#fff,stroke:#a30000;
    classDef bucket fill:#232F3E,color:#fff,stroke:#0f151d;
    classDef mq fill:#FF6600,color:#fff,stroke:#b34700;
    class Oracle store;
    class S3 bucket;
    class MQ mq;
```

RabbitMQ y Oracle no están definidos como servicios en `docker-compose.yml`: se asumen externos/pre-existentes. El acceso a Oracle pasa por un túnel SSH standalone (`stack/ssh_tunnel/bd-tunnel.sh` + su propio `.env`, llave en `stack/keys/bd.pem`), fuera del stack de Compose.

**Stack tecnológico:**

| Capa               | Tecnología                                                          |
| ------------------- | ---------------------------------------------------------------------- |
| API                | FastAPI + Uvicorn                                                      |
| Mensajería         | RabbitMQ (aio-pika)                                                    |
| Base de datos      | Oracle DB (`python-oracledb` async)                                    |
| Almacenamiento     | AWS S3 (`boto3`)                                                       |
| Scraping           | `aiohttp` (requests crudos, sin navegador)                             |
| Conversión a PDF   | LibreOffice headless (Word/Excel), `wkhtmltopdf` (HTML), PyMuPDF/Pillow (imágenes) |
| Comprimidos        | `zipfile`, `rarfile` (+ `unar`), `py7zr` — extracción recursiva con subcarpetas |
| Inyección deps.    | `dependency-injector`                                                  |
| Infraestructura    | Docker Compose                                                         |

---

## Servicios

### ms_ekogui

Microservicio REST que dispara el scraping: resuelve entidades/procesos a consultar y publica un mensaje por página en la cola de scrape. Es **stateless** — no tiene base de datos propia, solo produce mensajes.

- **Puerto:** `8000`
- **Framework:** FastAPI
- **Prefijo API:** `/api/v1/ekogui`
- **Publica en:** `QUEUE_SCRAPE_NAME`

Ver endpoints en [API Reference](#api-reference).

---

### bot

Consumidor de `QUEUE_SCRAPE_NAME` (5 réplicas). Por cada mensaje (`EkoguiReq` = una página de procesos de **una sola entidad**):

1. Abre **una sola sesión** en Ekogui (login + SSO + selección de entidad) y la reutiliza para todos los procesos del lote — no se loguea por cada proceso individual.
2. Por cada proceso: lista sus documentos de soporte y, por cada documento, resuelve su URL descargable (`obtenerUrlDocumento`). Esta llamada reintenta con backoff si el gateway Zuul de Ekogui responde con un 500 transitorio (`SHORTCIRCUIT`/`GENERAL` — el backend/SGD está lento o caído), y valida que la respuesta sea una URL `http(s)` real antes de usarla, para no publicar basura en la cola si Ekogui falla.
3. Arma un `ActuacionDto` (evolución procesal) y un `AutoItemDto{fechaAuto, urlAuto}` por documento.
4. Publica actuaciones a `COLL_QUEUE_NAME` (verificando primero contra `TB_ACTUACIONES_RAMA` que no exista ya) y autos a `AUTOS_QUEUE_NAME` (un mensaje por radicado, con la lista completa de autos nuevos, verificando contra `TB_CONTROL_AUTOS_RAMA`).
5. Si un proceso o documento individual falla, se loguea y se continúa con el resto del lote — no aborta el mensaje completo.

**Payload publicado a `QUEUE_SCRAPE_NAME`** (consumido por `bot`, publicado por `ms_ekogui`):

```json
{
  "entidadId": 405,
  "entidadNombre": "ADMINISTRADORA COLOMBIANA DE PENSIONES",
  "estado": "ACTIVO",
  "procesos": [
    {
      "procesoId": 2568417,
      "numeroProceso": "47001310500420240012300",
      "despachoInicialNombre": "JUZGADO 04 LABORAL DEL CIRCUITO DE SANTA MARTA",
      "entidadId": 405,
      "entidadNombre": "ADMINISTRADORA COLOMBIANA DE PENSIONES"
    }
  ]
}
```

**Payload publicado a `COLL_QUEUE_NAME`** (consumido por `collector_ekogui`):

```json
{
  "RADICADO_RAMA": "47001310500420240012300",
  "COD_DESPACHO_RAMA": "JUZGADO 04 LABORAL DEL CIRCUITO DE SANTA MARTA",
  "FECHA_ACTUACION": "10-07-2024",
  "ACTUACION_RAMA": "AUTO ADMISORIO",
  "ANOTACION_RAMA": "INFORMACION DESCARGADA EKOGUI",
  "ORIGEN_DATOS": "EKOGUI"
}
```

**Payload publicado a `AUTOS_QUEUE_NAME`** (consumido por `downloader_autos`):

```json
{
  "radicacion": "47001310500420240012300",
  "despacho": "JUZGADO 04 LABORAL DEL CIRCUITO DE SANTA MARTA",
  "origen": "EKOGUI",
  "autos": [
    { "fechaAuto": "2024-07-10", "urlAuto": "https://services.defensajuridica.gov.co/.../mercurio/consulta/imagen?g=9a22e66c2513b991deb0c6d28472db49" }
  ]
}
```

---

### collector_ekogui

Consumidor de `COLL_QUEUE_NAME`. A diferencia de los demás bots, no inserta actuación por actuación: las acumula en memoria y hace *flush* en batch (lo que ocurra primero: `BATCH_SIZE` mensajes acumulados o `FLUSH_INTERVAL` segundos transcurridos), llamando al procedimiento almacenado Oracle `LITI.INSERT_MASIVOS.CARGUE_MASIVO` con el batch serializado como JSON y el `TIPO_CARGUE` configurado. Si el insert falla, el batch se vuelve a encolar al frente del buffer para reintentar en el siguiente flush, en vez de perderse.

---

### downloader_autos

Consumidor de `AUTOS_QUEUE_NAME` (5 réplicas). Por cada auto del lote:

- Descarta si ya existe en `TB_CONTROL_AUTOS_RAMA` por URL (`checkAutoExist`).
- Descarga el documento (`httpClient.fetchDocument`) detectando el tipo real de contenido por `Content-Type`, o por firma binaria si el servidor lo declara vacío/genérico.
- Lo convierte a PDF según su tipo real — ver [tabla de tipos soportados](#tipos-de-archivo-soportados-en-downloader_autos) — **sin tocar su contenido**, solo el contenedor/formato.
- Calcula SHA-256 del PDF resultante y descarta duplicados (dentro del mismo lote y contra `TB_CONTROL_AUTOS_RAMA`).
- Renombra a `{fecha}_{radicación}_{consecutivo}.pdf`, sube a S3 (prefijo `S3_PREFIX_AUTOS`) e inserta el registro.
- Si un ítem falla, se loguea y se continúa con el resto del lote; al final se loguea un resumen (`insertados` / `omitidosPorUrl` / `omitidosPorHash` / `omitidosPorPdfInvalido` / `omitidosPorNoDisponible` / `errores`).

---

## Tipos de Archivo Soportados en downloader_autos

| Tipo real detectado                          | Procesador           | Conversión                                                  |
| ---------------------------------------------- | ---------------------- | -------------------------------------------------------------- |
| PDF                                            | `PdfProcessor`        | Ninguna, se guarda tal cual                                   |
| Word (`.doc`/`.docx`/`.docm`)                 | `DocxProcessor`       | LibreOffice headless                                           |
| Excel (`.xls`/`.xlsx`/`.xlsm`)                 | `XlsxProcessor`       | LibreOffice headless (solo lectura de metadatos, sin reestilar celdas) |
| Imagen (`png`/`jpg`/`webp`/`gif`/`bmp`/`tiff`) | `ImageProcessor`      | Se envuelve en una página PDF, sin OCR ni reprocesar píxeles   |
| HTML (o un `.xls` que en realidad es una tabla HTML — quirk conocido de SGDEA) | `HtmlXlsProcessor`    | `wkhtmltopdf`                                                  |
| Comprimido (`.zip`/`.rar`/`.7z`)               | `CompressedProcessor` | Extracción recursiva (subcarpetas y comprimido-dentro-de-comprimido con tope de profundidad); cada archivo interno soportado se convierte con el procesador que le corresponda |

El comprimido en sí **nunca** se sube ni recibe consecutivo — solo sus archivos internos. Cada uno conserva la fecha y el radicado del auto original, pero recibe su propio consecutivo, y su URL guardada incluye el nombre del archivo interno (`"<url-del-zip>#<archivo>"`) para que un reproceso nunca descarte el zip completo solo porque uno de sus archivos ya quedó insertado.

Cuando el `Content-Type` que declara el servidor viene vacío o genérico (`application/octet-stream`), el tipo real se infiere por firma binaria (`ContentTypeSniffer`) antes de decidir qué procesador usar.

---

## Nomenclatura de Archivos

`downloader_autos` nombra cada PDF final así:

```
{fecha dd-mm-yyyy}_{radicación}_{consecutivo}.pdf
```

El `consecutivo` es por combinación `radicación + fecha` y se calcula consultando el máximo ya registrado en `TB_CONTROL_AUTOS_RAMA` (`maxConsecutive`), cacheado en memoria mientras dura el procesamiento del lote para no repetir consultas para el mismo radicado. Cuando un auto viene de un comprimido con varios archivos, cada archivo interno recibe su propio consecutivo dentro de esa misma combinación radicación+fecha.

---

## Configuración del Entorno

Cada módulo requiere un archivo `.env` en su directorio raíz (no se incluyen en el repositorio).

### ms_ekogui `.env`

```env
# RabbitMQ
RABBITMQ_HOST=
RABBITMQ_PORT=
QUEUE_SCRAPE_NAME=
RABBIT_USER=
RABBIT_PASSWORD=

# Credenciales Ekogui
EKOGUI_DOCUMENT_TYPE=
EKOGUI_DOCUMENT_NUMBER=
EKOGUI_PASSWORD=

# Certificado SSL intermedio compartido
SSL_INTERMEDIATE_CERT_PATH=
```

---

### bot `.env`

```env
# RabbitMQ
RABBITMQ_HOST=
RABBITMQ_PORT=
QUEUE_SCRAPE_NAME=
AUTOS_QUEUE_NAME=
COLL_QUEUE_NAME=
PREFETCH_COUNT=
RABBIT_USER=
RABBIT_PASSWORD=

# Oracle DB
DB_USERNAME=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_NAME=
DB_POOLED=

# Tablas
TB_ACTUACIONES_RAMA=
TB_CONTROL_AUTOS_RAMA=

# Credenciales Ekogui
EKOGUI_DOCUMENT_TYPE=
EKOGUI_DOCUMENT_NUMBER=
EKOGUI_PASSWORD=

# Certificado SSL intermedio compartido
SSL_INTERMEDIATE_CERT_PATH=

# Proxies salientes (JSON array opcional, ej. ["http://user:pass@host:port"])
PROXIES=
```

> `QUEUE_SCRAPE_NAME` debe coincidir con el mismo campo en `ms_ekogui`. `AUTOS_QUEUE_NAME` debe coincidir con `NOT_AUTOS_QUEUE_NAME` de `downloader_autos`, y `COLL_QUEUE_NAME` con `QUEUE_COLL_NAME` de `collector_ekogui`.

---

### collector_ekogui `.env`

```env
# RabbitMQ
RABBITMQ_HOST=
RABBITMQ_PORT=
QUEUE_COLL_NAME=
PREFETCH_COUNT=
RABBIT_USER=
RABBIT_PASSWORD=

# Oracle DB
DB_USERNAME=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_NAME=
DB_POOLED=

# Batching hacia CARGUE_MASIVO
BATCH_SIZE=
FLUSH_INTERVAL=
TIPO_CARGUE=
```

---

### downloader_autos `.env`

```env
# RabbitMQ
RABBITMQ_HOST=
RABBITMQ_PORT=
NOT_AUTOS_QUEUE_NAME=
PREFETCH_COUNT=
RABBIT_USER=
RABBIT_PASSWORD=

# Oracle DB
DB_USERNAME=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_NAME=
DB_POOLED=

# Tablas
TB_CONTROL_AUTOS_RAMA=

# Archivos temporales
FOLDER=

# AWS S3
S3_BUCKET_ABBY=
S3_PREFIX_AUTOS=
S3_SECRET=
S3_ACCESS_KEY=

# Proxies salientes (opcional)
PROXIES=
```

---

## Despliegue

### Requisitos previos

- Docker Engine >= 24
- Docker Compose V2 (`docker compose`)
- Archivos `.env` configurados en cada módulo
- **RabbitMQ** y **Oracle** accesibles desde la red del host — no están definidos como servicios en `docker-compose.yml`, se asumen externos/pre-existentes. El túnel SSH hacia la base de datos es un script standalone (`stack/ssh_tunnel/bd-tunnel.sh`), fuera del stack de Compose.

### Levantar el stack

```bash
docker compose up -d
```

### Construir imágenes sin caché

```bash
docker compose build --no-cache
docker compose up -d
```

### Ver logs en tiempo real

```bash
# Todos los servicios
docker compose logs -f

# Servicio específico
docker compose logs -f bot
docker compose logs -f downloader_autos
```

### Detener y limpiar

```bash
docker compose down
```

---

## API Reference

Base URL: `http://localhost:8000`

---

### `GET /`

Health-check simple, usado por el `healthcheck` de compose.

```bash
curl 'http://localhost:8000/'
```

---

### `POST /api/v1/ekogui/allWithScraper`

Resuelve entidades/procesos y publica un mensaje por página en `QUEUE_SCRAPE_NAME`.

| Campo        | Tipo                    | Requerido | Descripción                                             |
| ------------- | ------------------------ | :--------: | ----------------------------------------------------------- |
| `entidades`  | `"todos"` \| `int[]`    | ✅         | IDs de entidad a consultar, o `"todos"` para el catálogo completo |
| `estado`     | `str`                    | ✅         | Estado de los procesos a filtrar                             |
| `batchSize`  | `int`                    | ❌ (`10`)  | Cantidad de procesos por página/mensaje publicado            |

```bash
curl -X POST 'http://localhost:8000/api/v1/ekogui/allWithScraper' \
  -H 'Content-Type: application/json' \
  -d '{
    "entidades": "todos",
    "estado": "ACTIVO",
    "batchSize": 10
  }'
```

**Respuesta** (`202 Accepted`):

```json
{
  "entidades": "todos",
  "estado": "ACTIVO",
  "extraidos": 214,
  "lotesPublicados": 22,
  "entidadesConError": []
}
```

---

### `POST /api/v1/ekogui/searchCaseNumber`

Publica un job de búsqueda de un radicado puntual dentro de una entidad.

```bash
curl -X POST 'http://localhost:8000/api/v1/ekogui/searchCaseNumber' \
  -H 'Content-Type: application/json' \
  -d '{
    "entidadId": 405,
    "radicado": "47001310500420240012300",
    "estado": "ACTIVO"
  }'
```

---

## Resiliencia

- **Consumo de colas** (`RabbitMQConsumer`): usa `aio_pika.connect_robust` (reconexión automática de la conexión AMQP) y ack manual por mensaje; si el handler lanza una excepción, el mensaje se rechaza sin reencolar (`nack(requeue=False)`) y queda registrado en el log — no hay reintento automático a nivel de mensaje.
- **Procesamiento por lote, tolerante a fallos puntuales**: `ScraperService`, `CollectorService` y `AutosDownloaderService` envuelven cada ítem del lote en su propio `try/except` — si un proceso, actuación o auto individual falla, se loguea y se continúa con el resto en vez de abortar todo el mensaje; al final de cada lote se loguea un resumen con conteos.
- **Deduplicación en 2 niveles** (`bot` y `downloader_autos`): por hash/URL dentro del mismo lote, y contra Oracle (evita reprocesar algo ya insertado en una corrida anterior).
- **Reintento en `bot`**: la resolución de la URL de cada documento reintenta con backoff ante un 500 transitorio del gateway Zuul de Ekogui, en vez de propagar el error o publicar una URL inválida.
- **`downloader_autos` ante archivos parciales de un comprimido**: si falla la subida de un archivo dentro de un zip, el resto del zip se reintenta en el siguiente reproceso (no se marca el zip completo como ya hecho por tener solo un archivo insertado).

---

## Escalado Horizontal

`bot` y `downloader_autos` están diseñados para correr con múltiples réplicas (`deploy.replicas` en `docker-compose.yml`), repartiendo el consumo de sus colas respectivas vía `PREFETCH_COUNT`. `ms_ekogui` y `collector_ekogui` corren como instancia única.

```bash
docker compose up -d \
  --scale bot=5 \
  --scale downloader_autos=5
```

---

## Autor

Desarrollado y mantenido por **Samuel Monsalve** (único desarrollador del proyecto) — [samuel.monsalve@litigando.com](mailto:samuel.monsalve@litigando.com).

---

<div align="center">
  <sub>Litigando · 2026</sub>
</div>
</div>
