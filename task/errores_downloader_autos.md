# Errores servicio `downloader_autos` (5 réplicas) — últimas 24h

Total líneas ERROR: **9,834**
Fuente: `docker compose logs --since 24h`

---

## 1. 404 al descargar el archivo temporal — 5,186 casos ✅ ARREGLADO

> Fix aplicado en `httpClient.py::_fetchBinary`: backoff creciente entre
> reintentos (sin retrasar el primer intento) + tratar cuerpo vacío como
> fallo retryable (esto último también ataca el punto 2 de abajo).

Ocurre en `httpClient.py::_fetchBinary` (2 intentos, sin backoff) al pedir el
PDF real bajo `/mercurio/imagenesapp/temporales/<hash>.pdf`, después de leer
el `<embed>` de la página intermedia `imagen?g=<hash>`.

**Causa probable:** el archivo temporal se pide de inmediato, sin esperar a
que SGDEA termine de generarlo, y el retry es instantáneo (mismo problema).

**Fix sugerido:** agregar una pequeña espera antes del primer intento y
backoff real entre reintentos en
`downloader_autos/app/infrastructure/http/httpClient.py:173-193`.

```
downloader_autos-4  | 2026-07-31 05:02:27,102 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=76001310501120240045800 fecha=2025-02-14 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=54ad0111a10ce95dcb892ee5dbcdca71: Descarga fallida tras 2 intentos - https://sgdea.defensajuridica.gov.co/mercurio/imagenesapp/temporales/00000000000000426634.pdf: 404, message='', url='https://sgdea.defensajuridica.gov.co/mercurio/imagenesapp/temporales/00000000000000426634.pdf'
downloader_autos-4  | 2026-07-31 05:02:28,005 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=76001310501120240045800 fecha=2025-02-14 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=d713dc21bf72a5a2d7b3461ee58a3713: Descarga fallida tras 2 intentos - https://sgdea.defensajuridica.gov.co/mercurio/imagenesapp/temporales/00000000000000426614.pdf: 404, message='', url='https://sgdea.defensajuridica.gov.co/mercurio/imagenesapp/temporales/00000000000000426614.pdf'
downloader_autos-4  | 2026-07-31 05:02:30,468 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=76001310501120240045800 fecha=2025-02-14 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=e7d47234df31c8c81cb1d92e7331e1ad: Descarga fallida tras 2 intentos - https://sgdea.defensajuridica.gov.co/mercurio/imagenesapp/temporales/00000000000000426604.pdf: 404, message='', url='https://sgdea.defensajuridica.gov.co/mercurio/imagenesapp/temporales/00000000000000426604.pdf'
```

---

## 2. Archivo descargado vacío o no encontrado en disco — 4,435 casos ✅ ARREGLADO

> Fix aplicado: el punto 1 ya cubría el caso del archivo temporal
> (`_fetchBinary`). Se agregó el mismo chequeo de "cuerpo vacío -> reintentar
> con backoff" en `fetchDocument` para el otro camino posible (binario
> directo desde `imagen?g=<hash>`, sin pasar por archivo temporal), que antes
> no tenía ningún reintento y devolvía el vacío como válido.

Se lanza en `PdfProcessor.py::saveRawFile` (líneas 29-30): la petición HTTP
responde 200 pero el contenido escrito a disco pesa 0 bytes.

**Causa probable:** mismo origen que el punto 1 — se pide el binario antes
de que el servidor lo tenga listo, pero en este caso responde 200 con
cuerpo vacío en lugar de 404.

**Fix sugerido:** en `_fetchBinary`, validar que `content` no esté vacío
antes de darlo por válido; si viene vacío, tratarlo como fallo y reintentar
con backoff (mismo fix que el punto 1).

```
downloader_autos-4  | 2026-07-31 04:59:03,871 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=76001310501020240046200 fecha=2026-07-16 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=e31849c607fc09bc4194fbcce5395efc: ❌ Error al guardar el archivo PDF: ❌ Archivo descargado vacío o no encontrado en disco: temp/76001310501020240046200_1f0179c9bb544aa0a4a2dc04c4ad438a/tmp_68e938719c9847ab9bd3367054902c5b.pdf
downloader_autos-4  | 2026-07-31 04:59:08,345 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=76001310501020240046200 fecha=2025-03-02 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=e9f1c56b686031c825f3dcd9e09f6f2e: ❌ Error al guardar el archivo PDF: ❌ Archivo descargado vacío o no encontrado en disco: temp/76001310501020240046200_1f0179c9bb544aa0a4a2dc04c4ad438a/tmp_aebf4714baa34b23be0f8a95668dcfc5.pdf
downloader_autos-4  | 2026-07-31 04:59:12,536 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=76001310501020240046200 fecha=2025-02-21 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=3eae52963128e4a9f7464236d11f65eb: ❌ Error al guardar el archivo PDF: ❌ Archivo descargado vacío o no encontrado en disco: temp/76001310501020240046200_1f0179c9bb544aa0a4a2dc04c4ad438a/tmp_30d9267d831e4d1e8c24fc542cf3bcd9.pdf
```

---

## 3. 502 Bad Gateway — 193 casos ✅ ARREGLADO

Error transitorio del gateway al pedir la página intermedia `imagen?g=<hash>`.

> **Corrección sobre la nota original:** decía "ya se reintenta 2 veces",
> pero no era cierto — `fetchDocument` no tenía ningún `try/except` alrededor
> del `raise_for_status()`, así que un 502 se propagaba de inmediato en el
> primer intento (los "2 intentos" son de `_fetchBinary`, un paso posterior
> para el archivo temporal, no éste). Se agregó retry con backoff para
> status 502/503/504 (transitorios de gateway); los demás status (403, 404,
> etc.) siguen sin reintentar porque no son transitorios.

```
downloader_autos-4  | 2026-07-31 02:00:11,326 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=23001310500320250005300 fecha=2026-01-21 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=18fc2b2e112ad297374465545b2377e8: 502, message='Bad Gateway', url='https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=18fc2b2e112ad297374465545b2377e8'
downloader_autos-4  | 2026-07-31 02:00:11,612 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=23001310500320250005300 fecha=2026-01-21 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=8a39d849dbb3a79ba9e0c9215b949d4f: 502, message='Bad Gateway', url='https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=8a39d849dbb3a79ba9e0c9215b949d4f'
```

---

## 4. "No hay procesador definido" (content-type sin mapear) — 9 casos ✅ ARREGLADO

`ProcessorFactory.py:25` no tenía entrada en `processorMap` para
`application/octet-stream` (el sniffing por firma binaria ya se intenta en
`_resolvedContentType`, pero si no reconoce ninguna firma conocida, se queda
en `application/octet-stream` y no hay processor para eso).

> **Intento 1 (revertido):** mapear `application/octet-stream` directo a
> `pdfProcessor`. Se descartó porque, al bajar manualmente estas URLs, se
> confirmó que en la práctica son `.docx` — y `PdfProcessor.toPdf()` es un
> passthrough que NO convierte nada; el archivo hubiera terminado
> descartado en silencio como `omitidosPorPdfInvalido` (sin error visible)
> en vez de convertirse, perdiendo el documento real.
>
> **Fix aplicado:** se agregó `ContentTypeSniffer.byExtension()` como
> último fallback en `_resolvedContentType` (`httpClient.py`): si ni el
> Content-Type declarado ni la firma binaria resuelven el archivo, se usa
> la extensión del nombre real (`temporales/<archivo>.docx` o
> Content-Disposition) contra el mismo mapa que ya usa `forLocalFile`. Así
> un `.docx` no identificado por firma cae en `docxProcessor` (que sí
> convierte con LibreOffice), no en `pdfProcessor`.

```
downloader_autos-4  | 2026-07-31 05:04:11,783 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=05001310501620220043500 fecha=2025-03-12 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=2393a60179c918343d068b50fa2febac: No hay procesador definido para tipo 'application/octet-stream' y url 'https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=2393a60179c918343d068b50fa2febac'
downloader_autos-4  | 2026-07-31 05:06:55,318 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=27001233300020180006800 fecha=2025-02-26 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=9703eadd9a85d63db126ca4be7e69bd1: No hay procesador definido para tipo 'application/octet-stream' y url 'https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=9703eadd9a85d63db126ca4be7e69bd1'
```

---

## 5. Excepción sin mensaje (bare exception) — 11 casos ✅ MEJORADO (diagnóstico)

Igual estructura que el punto 1/2 pero el mensaje de excepción queda vacío
(`str(e)` vacío, típico de `asyncio.TimeoutError()`/`CancelledError()` sin
texto). Volumen bajo, no crítico, pero antes era imposible saber la causa.

> Fix aplicado: método `_describeError()` en `AioHttpClient` (`httpClient.py`)
> que antepone siempre el tipo de excepción (`type(e).__name__`) cuando
> `str(e)` viene vacío. Aplicado en los mensajes de reintento y en el
> `RuntimeError` final de `_fetchBinary`. No elimina el error (sigue siendo
> un timeout/cancelación transitoria), pero la próxima vez el log va a decir
> qué tipo de excepción fue en vez de quedar en blanco.

```
downloader_autos-2  | 2026-07-30 16:52:38,226 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=47001310500120230004500 fecha=2024-06-18 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=dcfcd69adaade93b9ba835a0d2351a1e:
downloader_autos-4  | 2026-07-30 17:43:44,225 - ERROR - [AutosDownloaderService] - 🔴 Error descargando auto - radicacion=13001333301120250022000 fecha=2026-04-07 url=https://sgdea.defensajuridica.gov.co/mercurio/consulta/imagen?g=cf5de1ad5827d1223c039fb13caee7ae:
```
