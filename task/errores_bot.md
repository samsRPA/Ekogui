# Errores servicio `bot` (scraper Ekogui, 5 réplicas) — últimas 24h

Total líneas ERROR: **1,541**
Fuente: `docker compose logs --since 24h`

---

## 1. Error resolviendo archivoId → RuntimeError status=403 Forbidden — 1,172 casos ✅ ARREGLADO

Se lanzaba en `EkoguiScraper.py::obtenerUrlDocumento` cuando el gateway
respondía 403 al pedir la URL del documento.

**Causa:** el `idToken` de la sesión (obtenido una sola vez por mensaje/lote
en `iniciarSesionEntidad`) expira a mitad de lotes largos, y las llamadas
restantes del mismo lote empiezan a dar 403.

> Fix aplicado:
> - Nueva excepción `SesionExpiradaError` (`IEkoguiScraper.py`) para
>   distinguir un 403 de otros errores sin parsear texto.
> - `EkoguiScraper.py`: tanto `obtenerUrlDocumento` como
>   `listarDocumentosProceso` (que antes ni chequeaba el status) ahora
>   lanzan esta excepción en 403.
> - `ScraperService.py::_processProceso`: captura `SesionExpiradaError`,
>   refresca la sesión (`_refrescarSesion`) UNA vez por proceso y reintenta
>   la misma llamada. El token refrescado se propaga a `_process` para que
>   el resto del lote (los siguientes procesos) lo use, sin volver a
>   loguearse en cada uno.
>
> Como bonus, esto también debería reducir el punto 2 (`AttributeError`):
> `listarDocumentosProceso` ya no devuelve silenciosamente un body invalido
> cuando la sesión expiró a mitad de lote.

```
bot-5               | 2026-07-30 12:57:21,949 - ERROR - [ScraperService] - 🔴 Error resolviendo archivoId=11870210 de radicado=05001400500920260029800 (procesoId=2780682); se continua
bot-5               | Traceback (most recent call last):
bot-5               |   ...
bot-5               |     raise RuntimeError(
bot-5               | RuntimeError: Respuesta invalida al resolver URL de documento (status=403 procesoId=2568205 archivoId=10037761): ''
```

---

## 2. Error procesando procesoId → AttributeError: 'str' object has no attribute 'get' — 264 casos ✅ ARREGLADO

**BUG DE CÓDIGO.** `EkoguiScraper.py::listarDocumentosProceso` hacía
`return await resp.json(content_type=None)` sin validar el tipo de dato. Si
la API respondía con un string (p.ej. mensaje de error) en vez de una lista
de documentos, `ScraperService.py::_processProceso` iteraba ese string
carácter por carácter, y cada carácter (un `str`) explotaba en
`doc.get("archivoId")`.

**Causa raíz principal:** la sesión expirada (403) del punto 1 — ya
arreglada ahí, y `listarDocumentosProceso` ahora chequea el status 403
explícitamente antes de parsear el body.

> Fix adicional aplicado (defensa en profundidad): en
> `listarDocumentosProceso`, tras parsear el JSON se valida que sea
> `list[dict]`; si no lo es (por cualquier otro motivo, no solo 403), se
> lanza un `RuntimeError` claro con el body real en vez de dejar que
> reviente más adelante como este `AttributeError` confuso. El proceso se
> salta igual que antes (mismo manejo en `_process`), pero ahora el log
> dice qué pasó de verdad.

```
bot-5               | 2026-07-31 04:46:54,428 - ERROR - [ScraperService] - 🔴 Error procesando procesoId=2542902 (23001333301020230001900); se continua con el resto del lote
bot-5               | Traceback (most recent call last):
bot-5               |   File "/app/app/application/services/ScraperService.py", line 60, in _process
bot-5               |     documentosCount, actuacionesCount = await self._processProceso(proceso, client, idToken)
bot-5               |   File "/app/app/application/services/ScraperService.py", line 218, in _processProceso
bot-5               |     archivoId = doc.get("archivoId")
bot-5               |                 ^^^^^^^
bot-5               | AttributeError: 'str' object has no attribute 'get'
```

---

## 3. Error resolviendo archivoId → RuntimeError status=500 (Zuul) tras agotar reintentos — 55 casos ✅ ARREGLADO

Documentado en el propio código como transitorio (backend/SGD lento o
caído). Tenía retry con backoff (3 intentos), pero **solo se activaba si el
body matcheaba un regex muy específico** (`"exception":
"com.netflix.zuul.exception.ZuulException"`). En los logs aparece otra
forma de 500 que no matchea ese regex:

```json
{"message":"error.internalServerError","description":"Internal server error","fieldErrors":null}
```

Para ese caso, aunque el status era 500, **nunca se reintentaba** — fallaba
al primer intento. No era "se agotaron los 3 reintentos", era que ni
siquiera entraban al retry.

> Fix aplicado en `EkoguiScraper.py::obtenerUrlDocumento`: se quitó la
> dependencia del regex específico de Zuul; ahora se reintenta ante
> **cualquier 5xx** (`resp.status >= 500`), sin importar la forma exacta del
> body — cualquier 500 del backend es igual de transitorio. Se eliminó
> `_ZUUL_ERROR_RE` (quedó sin ningún otro uso en el archivo).

---

## 4. Error resolviendo archivoId → TimeoutError — 12 casos

Timeout/cancelación de conexión aiohttp al pedir la URL del documento
(`asyncio.exceptions.CancelledError` dentro de `wait_for`). Red/latencia
puntual, bajo volumen.

---

## 5. "No se pudo iniciar sesion en ekoguims (status=404)" — 18 casos

Lanzado en `EkoguiScraper.py::_signInModule` (línea 224) cuando el SSO al
módulo `/ekoguims` responde 404 en vez de loguear. Concentrado en dos
ráfagas cortas (30-jul 16:34 y 21:09-21:10) — parece una caída puntual del
servicio externo `services.defensajuridica.gov.co`, no un bug de código.

```
bot-1               | 2026-07-30 16:34:09,449 - ERROR - [RabbitMQConsumer] - 🔴 Error procesando mensaje: No se pudo iniciar sesion en https://services.defensajuridica.gov.co/ekoguims (status=404)
bot-1               |     raise RuntimeError(f"No se pudo iniciar sesion en {moduleBaseUrl} (status={resp.status})")
bot-1               | RuntimeError: No se pudo iniciar sesion en https://services.defensajuridica.gov.co/ekoguims (status=404)
```

---

## 6. "Error procesando mensaje" (genérico, sin submensaje) — 18 casos

Wrapper de excepción no clasificada en `ScraperService.py::handleMessage`
(línea 44). Bajo volumen, requiere revisar traceback caso a caso si
reaparece con frecuencia.
