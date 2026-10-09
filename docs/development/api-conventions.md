# Convenciones de API

Respuestas, errores, rate limiting, logging y utilitarios (paginación, uploads, límites, contexto). Léelo antes de crear o cambiar un endpoint. El contrato público (dónde va cada parámetro, filtros, fechas, orden) está en [api-contract.md](api-contract.md).

## Respuestas (`app/utils/response.py`)

**Siempre** `response_model=ApiResponse[T]` y los helpers:

```python
return success(data=obj, message="Creado")          # {"data": ..., "message": ...}
return paginated(items, total=total, pagination=p)  # {"data": [...], "pagination": {...}}
return empty("Eliminado")                           # {"message": "Eliminado"}
```

Los campos de primer nivel con `None` se excluyen del JSON (`Field(exclude_if=...)`); los `None` dentro de
`data` se conservan. El esquema OpenAPI mantiene `data`/`message`/`pagination` tipados.

Estilo FastAPI moderno: `Annotated[...]` para `Query`/`File`/`Depends`, `Field(min_length=...)` sin `...`,
`status_code=status.HTTP_201_CREATED`.

## Errores (`app/exceptions/`)

**Siempre** `AppHttpException`, nunca `HTTPException`:

```python
raise AppHttpException("Usuario no encontrado", 404, {"user_id": user_id}, code="user_not_found")
raise AppHttpException("Demasiados intentos", 429, headers={"Retry-After": "60"}, code="rate_limited")
```

Formato único de error (handlers y middlewares usan `app/exceptions/responses.py`):

```json
{"detail": {
  "msg": "texto para el usuario",
  "type": "NotFound",
  "code": "user_not_found",
  "reason": "opcional",
  "errors": [{"field": "email", "message": "es obligatorio", "type": "missing"}],
  "request_id": "a1b2c3d4e5f60708",
  "context": {"...": "solo development"},
  "loc": {"file": "...", "function": "...", "line": 10, "code": "... (solo 500 no controlado, development)"}
}}
```

- `message`: seguro para el usuario. Nunca `str(e)` ahí; los detalles van a `context`.
- `context`: solo en development. `loc` (archivo/función/línea, del traceback): solo en los 500 no
  controlados y solo en development; los 4xx llevan solo `context`.
- `code` / `reason`: estables, snake_case, para que el frontend decida.
- 422 de validación: mensajes en español, sin el valor enviado (`input`).
- 5xx y excepciones no controladas: se loguean siempre, una sola vez, con el frame del proyecto.
- Middlewares: nunca envolver `await self.app(...)` en `except Exception`; responder con `error_response()`.

## Rate limiting (`app/core/rate_limit.py`)

```python
from app.core.rate_limit import rate_limit

@router.post("/login", dependencies=[rate_limit("5/minute")])
async def login(...): ...
```

- Límite por ruta (login, registro, endpoints costosos). El global por IP es `limit_req` de nginx.
- Clave: IP del cliente (`request.client.host`). Requiere uvicorn con `--forwarded-allow-ips` = IP del proxy.
- En memoria cada worker cuenta por separado: con varios workers usar `RATE_LIMIT_REDIS_ENABLED=True`
  (`uv sync --extra redis`, cliente redis-py) y/o `limit_req` de nginx (ya configurado).
- Fail-open: si el storage falla o está mal configurado, la request pasa y se loguea un warning.
- FastAPI resuelve las dependencias **después** de leer el body: el límite de la app no evita recibir
  bodies grandes. El freno duro es `limit_req` de nginx (+ `RequestSizeMiddleware`).

## Logging

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Operación completada")   # el request_id se agrega automáticamente
```

- `LOG_FORMAT=json` para agregadores. Una línea de access log por request (nivel según status).
- **Nunca se loguea el body** de las requests. Headers sensibles (lista fija + `is_sensitive_key`) y query
  params sensibles se enmascaran.
- El logger raíz usa el mismo handler a nivel WARNING (librerías con el mismo formato/JSON).

## Otros utilitarios

- **Listados** (paginación, filtros, orden): un modelo que hereda de `ListQuery` (`app/utils/list_query.py`),
  recibido con `Annotated[XxxListQuery, Query()]` → `?page=1&size=20&sort=-created_at` (`query.size`, `query.offset`,
  `query.sort_terms`; `page` ≤ 1 000 000; parámetros desconocidos → 422). SQL con `WhereBuilder`/`order_by`
  (`app/core/sql_filters.py`). Detalle: `docs/features/pagination.md`.
  Contrato público siempre `page`/`size` (nunca `limit`/`offset` en la URL); `limit`/`offset` solo como argumentos
  del model. Único env: `PAGINATION_MAX_SIZE` (hard cap 200 en código). Detalle: `docs/features/pagination.md`.
- **Uploads**: `await save_upload(file, allowed_types=[...], max_size_mb=2)` guarda por bloques;
  procesar y **siempre** `await anyio.Path(info["path"]).unlink(missing_ok=True)` en `finally`.
- **Límite de body**: `REQUEST_MAX_SIZE_MB` para toda la versión (igual a `client_max_body_size` de nginx;
  sin overrides por ruta). Para archivos más grandes, subir ambos.
- **ContextVars** (auditoría: quién/desde dónde/qué ruta): `from app.core.context import current_http_identifier,
  current_request_ip, current_user_id` (la capa de auth del proyecto debe hacer `current_user_id.set(...)`).

