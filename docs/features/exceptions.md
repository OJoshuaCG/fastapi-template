# Manejo de Excepciones

Todas las respuestas de error (handlers de excepciones y middlewares) salen de un único serializador (`app/exceptions/responses.py`) con el mismo formato. Las respuestas exitosas usan otro envelope (`ApiResponse`, ver [Formato de Respuestas](response-format.md)).

## Formato de error

```json
{
  "detail": {
    "msg": "Usuario no encontrado",
    "type": "NotFound",
    "code": "user_not_found",
    "reason": "…",
    "errors": [{"field": "email", "message": "…", "type": "…"}],
    "request_id": "a1b2c3d4e5f6a7b8",
    "context": {"user_id": 99}
  }
}
```

Un 500 no controlado en development agrega además `loc`:

```json
"loc": {"file": "app/routes/v1/test.py", "function": "unhandled_error", "line": 56, "code": "…"}
```

| Campo | Presencia | Descripción |
|---|---|---|
| `msg` | siempre | Texto para el usuario final. Si no se da, sale el mensaje por defecto del status. |
| `type` | siempre | Derivado de la frase HTTP del status (solo el 422 usa un nombre propio, `ValidationError`): `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `MethodNotAllowed`, `Conflict`, `ContentTooLarge`, `UnsupportedMediaType`, `ValidationError`, `TooManyRequests`, `InternalServerError`, `BadGateway`, `ServiceUnavailable`, `GatewayTimeout`. |
| `code` | opcional | Código estable en snake_case para que el frontend decida. |
| `reason` | opcional | Sub-causa estable (ej. `pool_exhausted`, `duplicate`). |
| `errors` | opcional | Errores por campo `{field, message, type}`, **sin el valor enviado**. |
| claves de `public` | opcional | Datos adicionales del contrato. |
| `request_id` | siempre que exista | Igual al header `X-Request-ID`. |
| `context` | **solo `APP_ENV=development`** | Datos de depuración (sanitizados). |
| `loc` | **solo 500 no controlado y `APP_ENV=development`** | Último frame del proyecto en el traceback (`_project_frame`). Los errores controlados (`AppHttpException`, 4xx) no lo llevan. |

## `AppHttpException`

Todo error esperado se lanza con `AppHttpException` (`from app.exceptions import AppHttpException`).

```python
AppHttpException(
    message: str = "Error interno del servidor",
    status_code: int = 500,
    context: Any = None,
    *,
    code: str | None = None,
    reason: str | None = None,
    errors: list[dict] | None = None,
    public: dict | None = None,
    headers: dict[str, str] | None = None,
)
```

**Públicos (llegan al cliente):** `message`, `code`, `reason`, `errors`, `public`, `headers`.
**Privado (logs, y respuesta solo en development):** `context`. `AppHttpException` no calcula ubicación: el archivo/línea de un error no controlado sale del traceback (en el log y, en development, en `loc`).

```python
raise AppHttpException("Usuario no encontrado", 404, {"user_id": user_id}, code="user_not_found")

raise AppHttpException("El email ya está en uso", 409, code="user_conflict")

raise AppHttpException(
    "No autenticado", 401, code="unauthenticated", headers={"WWW-Authenticate": "Bearer"}
)

raise AppHttpException(
    "Datos inválidos",
    422,
    code="invalid_fields",
    errors=[{"field": "start_date", "message": "debe ser anterior a end_date", "type": "value_error"}],
)

raise AppHttpException(
    "Ya existe una solicitud pendiente", 409, code="request_pending",
    public={"existing_id": 123},  # → detail.existing_id
)
```

Reglas:

- **Nunca pongas `str(e)` en `message`.** Puede filtrar SQL, rutas o datos internos. Eso va en `context`.
- En `context` van ids y datos útiles para depurar, **nunca el body entrante completo** (PII). De todas formas se sanitiza: las claves que contienen `password`, `secret`, `token`, `authorization`, `api_key`, etc. se enmascaran con `***` (`app/utils/dict_utils.py`).
- Las claves de `public` que choquen con los campos reservados (`msg`, `type`, `code`, ...) se ignoran.

### Re-mapear errores de capas inferiores

La capa de datos ya traduce los errores de BD (ver [Base de Datos](database.md#traducción-de-errores)). Para darles un mensaje de negocio, captura la excepción por `reason` o `code`:

```python
try:
    user_id = await self.users.create(data)
except AppHttpException as e:
    if e.reason == "duplicate":
        raise AppHttpException("El username o email ya está en uso", 409, code="user_conflict") from e
    raise
```

## Handlers

`register_exception_handlers(app)` registra cuatro handlers. Se llama en la app raíz y en cada sub-app versionada.

| Excepción | Handler | Respuesta |
|---|---|---|
| `AppHttpException` | `app_exception_handler` | Status, mensaje y campos de la excepción. |
| `RequestValidationError` | `validation_exception_handler` | 422, `code="validation_error"`, `msg="Error de validación: <campo> <mensaje>"`, `errors` en español. |
| `StarletteHTTPException` | `http_exception_handler` | 404/405 de rutas, 401 de docs protegidos, 413 del límite de body, `HTTPException` nativo. |
| `Exception` | `generic_exception_handler` | 500 genérico. En development, `context` (`type_error`, `exception`) y `loc` (último frame dentro de `app/`). |

### Errores de validación

FastAPI responde por defecto un 422 en inglés que incluye `input` (el valor enviado, que puede traer datos personales). `app/utils/validation_messages.py` lo convierte a mensajes en español y sin `input`:

```json
{
  "detail": {
    "msg": "Error de validación: page debe ser mayor o igual a 1",
    "type": "ValidationError",
    "code": "validation_error",
    "errors": [
      {"field": "page", "message": "debe ser mayor o igual a 1", "type": "greater_than_equal"},
      {"field": "size", "message": "debe ser un número entero", "type": "int_parsing"}
    ],
    "request_id": "…"
  }
}
```

`field` quita el prefijo `body`/`query`/`path`/`header`/`cookie` y une los niveles con `.` (ej. `items.0.price`).

## Logging de errores

- **5xx** (`AppHttpException` ≥ 500 y excepciones no controladas): siempre se registran. Las no controladas llevan traceback y se registran **una sola vez**, aunque la excepción suba de la sub-app a la raíz. El traceback duplicado de uvicorn se descarta.
- **4xx** de `AppHttpException` y 422: solo con `LOGGER_EXCEPTIONS_ENABLED=True`. Los 422 registran únicamente los nombres de los campos.

```
... [ERROR] app.exceptions.HandlerExceptions [a1b2c3d4e5f6a7b8] 10.0.0.5 | POST /api/v1/test/unhandled-error | 500 | RuntimeError: Error no controlado de ejemplo | app/routes/v1/test.py:56 en unhandled_error()
```

## Errores emitidos por el template

| `code` | Status | Origen |
|---|---|---|
| `validation_error` | 422 | Validación de Pydantic |
| `rate_limited` | 429 | `rate_limit()` |
| `db_unavailable` (`pool_exhausted` / `connection_lost`) | 503 | Base de datos |
| `db_timeout` (`statement_timeout`) | 504 | Base de datos |
| `business_rule` | 409 | `SIGNAL SQLSTATE '45000'` |
| `conflict` (`duplicate` / `integrity`) | 409 | Base de datos |
| `db_error` | 500 | Base de datos |
| `unsupported_file_type` | 415 | `save_upload()` |
| `file_too_large` | 413 | `save_upload()` |
| `user_not_found`, `user_conflict`, `invalid_fields` | 404 / 409 / 422 | Ejemplo de usuarios |

## Errores desde un middleware ASGI

Para responder un error desde un middleware ASGI con el mismo formato, usa `error_response`:

```python
from app.exceptions import error_response

await error_response(403, "IP bloqueada", code="ip_blocked")(scope, receive, send)
```

## Buenas prácticas

```python
# ✅
raise AppHttpException("Usuario no encontrado", 404, {"user_id": user_id}, code="user_not_found")

# ❌ Funciona (lo formatea http_exception_handler), pero sin code ni context
from fastapi import HTTPException
raise HTTPException(status_code=404, detail="Not found")

# ❌ Filtra detalles internos al cliente
raise AppHttpException(f"Error: {e}", 500)
```

- No captures `Exception` para devolver 500 a mano: deja que la maneje `generic_exception_handler`.
- Para reportar un error, el frontend usa `detail.request_id` (o el header `X-Request-ID`), que se busca directamente en los logs.

---

Ver también: [Logging](logging.md) · [Formato de Respuestas](response-format.md)
