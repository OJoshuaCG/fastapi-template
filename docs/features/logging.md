# Logging

Se usa `logging` estándar de Python. `configure_logging(settings)` (`app/core/logging_config.py`) lo configura una sola vez, al crear la app en `main.py`.

## Uso

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Pedido %s confirmado", order_id)      # el request_id se agrega solo
logger.warning("Reintento %d de %d", attempt, max_attempts)
logger.exception("Falló la sincronización")        # dentro de un except: incluye traceback
```

- Usa `logging.getLogger(__name__)` dentro del paquete `app`. El handler está configurado en el logger `app` (con `propagate=False`), así que cubre `app.*`. El logger raíz usa el mismo handler a nivel `WARNING`: los warnings de librerías (sqlalchemy, httpx, limits...) salen con el mismo formato (JSON consistente).
- Usa argumentos `%s` en vez de f-strings: el mensaje solo se formatea si el nivel está activo.
- No agregues el request id a mano: `RequestContextFilter` lo inyecta en cada línea desde el ContextVar (`-` fuera de una request).

## Formatos

```env
LOGGER_LEVEL=INFO        # DEBUG | INFO | WARNING | ERROR | CRITICAL
LOG_FORMAT=text          # text | json
```

**text** (default):

```
2026-09-29 10:30:15,123 [INFO] app.access [a1b2c3d4e5f6a7b8] 10.0.0.5 | GET /api/v1/users/15 | 200 | 4.2ms
```

**json**, una línea por evento, para Loki/ELK/Datadog:

```json
{"ts": "2026-09-29T10:30:15.123456+00:00", "level": "INFO", "logger": "app.access", "msg": "10.0.0.5 | GET /api/v1/users/15 | 200 | 4.2ms", "request_id": "a1b2c3d4e5f6a7b8"}
```

En JSON se agregan `user_id` (si `current_user_id` está establecido), `exc` (traceback) y cualquier campo pasado con `extra=`:

```python
logger.info("Pago aprobado", extra={"order_id": 42, "amount": 1500})
```

## Access log (`LoggerMiddleware`)

Middleware ASGI puro en la app raíz (logger `app.access`). Escribe **una línea por request**:

```
<ip> | <MÉTODO> <path> | <status> | <duración>ms [| query: ...] [| headers: ...]
```

- Nivel según el status: 5xx `ERROR`, 4xx `WARNING`, resto `INFO`.
- `/health` y `/ready` no se registran.
- **El body nunca se registra.** Los bodies traen contraseñas, tokens y datos personales, y cualquier lista de "campos sensibles" termina quedándose atrás.
- Query params: los valores de claves sensibles (`token`, `password`, `api_key`, `secret`...) se enmascaran (`token=%2A%2A%2A`).
- Headers: `Authorization`, `Cookie`, `Set-Cookie`, `Proxy-Authorization` y `X-Api-Key` siempre se muestran como `***`, además de cualquier header cuyo nombre coincida con una clave sensible (`is_sensitive_key`: `token`, `secret`, `password`, `api_key`...).

```env
LOGGER_MIDDLEWARE_ENABLED=True             # False = no se agrega el middleware
LOGGER_MIDDLEWARE_SHOW_HEADERS=False
LOGGER_MIDDLEWARE_SHOW_QUERY_PARAMS=True
LOGGER_MIDDLEWARE_SHOW_PATH_PARAMS=True    # True = /api/v1/users/15 · False = /api/v1/users/{user_id}
LOGGER_MIDDLEWARE_ERRORS_ONLY=False        # True = solo registra requests con status >= 400
```

El detalle de un error (mensaje, `context`, traceback) no lo escribe el access log: lo escriben los exception handlers.

## Logs de errores

```env
# Registrar también los errores controlados 4xx (los 5xx siempre se registran)
LOGGER_EXCEPTIONS_ENABLED=False
```

- `AppHttpException` ≥ 500 y excepciones no controladas: siempre se registran. Las `AppHttpException` con `code`, `reason` y `context` sanitizado; las no controladas con traceback y `archivo:línea en función()` del proyecto, una sola vez.
- `AppHttpException` 4xx y 422 de validación: solo con `LOGGER_EXCEPTIONS_ENABLED=True`.

Ver [Manejo de Excepciones](exceptions.md#logging-de-errores).

## uvicorn

- **Access log de uvicorn** (`uvicorn.access`): el template no lo filtra. En Docker uvicorn corre con `--no-access-log` (el access log es `app.access`, que ya excluye `/health` y `/ready`); en local puedes pasar el mismo flag.
- **`uvicorn.error`**: se descarta el `Exception in ASGI application` de las excepciones que ya registró el handler de 500, para no duplicar el traceback.

## Otros logs del template

| Logger | Qué registra |
|---|---|
| `app.lifespan` | Arranque/apagado: cliente HTTP, BD, advertencias de configuración (`startup_warnings`). |
| `app.core.rate_limit` | Warning si el storage del rate limit (Redis) no responde o está mal configurado. |
| `app.routes.health` | Warning con la causa cuando `/ready` responde 503. |
| `app.exceptions.HandlerExceptions` | Errores (ver arriba). |

## Buscar por request

El `request_id` aparece en cada línea, en el header `X-Request-ID` y en `detail.request_id` de cada error. Con nginx delante es el mismo `$request_id` del log de nginx.

```bash
docker compose logs api | grep a1b2c3d4e5f6a7b8
```

## Qué no loguear

- Bodies, contraseñas, tokens, headers de autenticación, datos personales completos.
- `str(e)` de errores de BD en mensajes al cliente (en logs sí, vía `context`).

`sanitize()` de `app/utils/dict_utils.py` enmascara recursivamente las claves sensibles de un dict antes de loguearlo:

```python
from app.utils.dict_utils import sanitize

logger.info("Payload a proveedor: %s", sanitize(payload))
```

---

Ver también: [Contexto de Request](context.md) · [Middlewares](middlewares.md)
