# Errores servicio `ms_ekogui` — últimas 24h

Total líneas ERROR: **1**
Fuente: `docker compose logs --since 24h`

---

## 1. Error listando procesos de entidad → TimeoutError/CancelledError — 1 caso

Timeout de conexión (aiohttp `wait_for` cancelado) al listar procesos de la
entidad 405 (ADMINISTRADORA COLOMBIANA DE PENSIONES). El propio código ya
contempla el error y sigue con la siguiente entidad sin detener el proceso.

**Causa probable:** latencia/caída puntual de red hacia el servicio externo.
Volumen insignificante (1 en 24h), no requiere acción.

```
ms_ekogui           | 2026-07-31 05:03:08,706 - ERROR - 🔴 Error listando procesos de entidadId=405 (ADMINISTRADORA COLOMBIANA DE PENSIONES); se continua con la siguiente entidad
ms_ekogui           | Traceback (most recent call last):
ms_ekogui           |   File "/usr/local/lib/python3.12/asyncio/tasks.py", line 520, in wait_for
ms_ekogui           |     return await fut
ms_ekogui           |   File "/usr/local/lib/python3.12/site-packages/aiohttp/client.py", line 858, in _request
ms_ekogui           |     resp = await handler(req)
ms_ekogui           |   File "/usr/local/lib/python3.12/site-packages/aiohttp/streams.py", line 705, in read
ms_ekogui           |     await self._waiter
ms_ekogui           | asyncio.exceptions.CancelledError
ms_ekogui           |     raise TimeoutError from exc_val
ms_ekogui           | TimeoutError
ms_ekogui           | 2026-07-31 05:03:08,736 - INFO - 🟢 publishOrder finalizado - entidades=[405] estado=PROCESO_ENTIDAD_ACTIVO -> extraidos=0 lotesPublicados=0 entidadesConError=[405]
```
