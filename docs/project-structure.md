# Estructura del Proyecto

## Vista General

```
fastapi-template/
├── app/
│   ├── controllers/
│   │   ├── __init__.py
│   │   └── user_controller.py       # UserController + UserControllerDep
│   ├── core/
│   │   ├── context.py               # ContextVars de la request (Request ID, IP, ruta, usuario...)
│   │   ├── database.py              # Engine async, Database (fetch_*, execute, transaction, SP)
│   │   ├── encryption.py            # encrypt/decrypt/rotate (MultiFernet, ENCRYPTION_KEYS)
│   │   ├── http_client.py           # ServiceClient: base de integraciones externas (httpx)
│   │   ├── encoding.py              # encode_id/decode_id, EncodedId / EncodedIdOut (sqids)
│   │   ├── logging_config.py        # Logging text/JSON con request_id
│   │   ├── rate_limit.py            # Dependencia rate_limit() (librería limits)
│   │   ├── environment.py          # Settings (pydantic-settings): todas las variables de entorno → settings
│   │   └── versioned_app.py         # Factory create_versioned_app()
│   ├── exceptions/
│   │   ├── __init__.py
│   │   ├── AppHttpException.py      # Excepción controlada de la app
│   │   ├── HandlerExceptions.py     # Handlers globales + register_exception_handlers()
│   │   └── responses.py             # Serializador único de errores {"detail": {...}}
│   ├── middleware/
│   │   ├── ContextMiddleware.py     # Request ID + ContextVars (ASGI puro)
│   │   ├── LoggerMiddleware.py      # Log de requests/responses (ASGI puro)
│   │   └── RequestSizeMiddleware.py # Límite de body (413)
│   ├── models/
│   │   ├── __init__.py
│   │   └── user_model.py            # UserModel: SQL directo async + UserModelDep
│   ├── routes/
│   │   ├── health.py                # /health (liveness) y /ready (readiness)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── routes.py            # build_v1_router()
│   │       ├── test.py              # Ejemplos (no se registran en producción)
│   │       └── users.py             # CRUD de ejemplo
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── user.py                  # UserCreate, UserUpdate, UserOut
│   ├── services/
│   │   ├── __init__.py              # Qué va en un service y qué está prohibido
│   │   └── httpbin_service.py       # Ejemplo de integración externa (borrar al iniciar)
│   └── utils/
│       ├── __init__.py
│       ├── dict_utils.py            # sanitize() de datos sensibles (logs, contexto de errores)
│       ├── file_upload.py           # save_upload() / save_uploads() async
│       ├── http.py                  # client_ip(scope), log_level_for_status(status)
│       ├── pagination.py            # PaginationParams, PaginationDep
│       ├── passwords.py             # encrypt_password() / verify_password() / reveal_password()
│       ├── response.py              # ApiResponse[T], success(), paginated(), empty()
│       └── validation_messages.py   # Mensajes de validación en español (422 y configuración)
├── database/                        # Esquema en SQL plano (sin ORM ni Alembic)
│   ├── README.md                    # Cómo se aplican los scripts y convenciones
│   ├── init/                        # NNN_descripcion.sql, se aplican en orden
│   │   └── 001_users.sql            # Tabla users
│   └── procedures/                  # Stored procedures: sp_nombre.sql
│       └── sp_user_stats.sql        # Ejemplo: DELIMITER, 2 result sets, SIGNAL
├── docker/
│   ├── nginx/
│   │   ├── nginx.conf               # Config global: logs con request_id, limit_req, gzip
│   │   └── conf.d/app.conf          # Server: upstream api:8000, /health|/ready, HTTPS comentado
│   └── scripts/
│       └── entrypoint.sh            # serve | <comando>
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Entorno de test (ENV_FILE=""), esquema (init + procedures), app, cliente
│   ├── test_architecture.py         # Reglas de capas (imports por AST)
│   ├── test_database.py             # Database: helpers, transacciones, SP, timeouts, pool
│   ├── test_encryption.py           # Cifrado, rotación, compatibilidad omnicanal, contraseñas
│   ├── test_environment.py         # Contrato Settings ↔ .env.example, secretos, uso de settings.X (AST)
│   ├── test_http.py                 # Request ID, errores, límites, rate limit, CORS, logs
│   ├── test_http_client.py          # ServiceClient: reintentos, traducción de errores (MockTransport)
│   ├── test_encoding.py             # Encoding de IDs públicos (sqids)
│   ├── test_logging.py              # Filtros de logging (sin BD)
│   ├── test_openapi.py              # Esquema OpenAPI (envelope tipado)
│   ├── test_settings.py             # Validación de configuración
│   └── test_users_api.py            # CRUD /api/v1/users y /ready
├── docs/                            # Documentación
├── uploads/                         # Temporales de upload (.gitkeep)
├── main.py                          # create_app(): lifespan, middlewares, montaje de versiones
├── pyproject.toml                   # Dependencias, Ruff, pytest (deprecaciones = error)
├── alembic.ini                      # Opcional: requiere `uv add alembic` (ver database/README.md)
├── uv.lock
├── .python-version                  # 3.14
├── .env.example                     # Referencia de variables de entorno
├── .pre-commit-config.yaml          # ruff, detect-secrets, hooks básicos
├── .dockerignore
├── Dockerfile                       # Multi-stage (builder con uv → runtime sin uv)
├── docker-compose.yml               # db, api, nginx
├── docker-compose.test.yml          # MariaDB de test (tmpfs, puerto 3307)
├── readme.md
└── CLAUDE.md
```

---

## Arquitectura por capas

```
Request → Routes → Controllers → (Services) → Models → Database
                                     └──► APIs externas (ServiceClient)
```

| Capa | Ubicación | Responsabilidad |
|---|---|---|
| Routes | `app/routes/` | Endpoints, validación con schemas, `ApiResponse[T]`; llaman un método del controller |
| Controllers | `app/controllers/` | Casos de uso: reciben schemas, orquestan models/services, errores con `AppHttpException` |
| Services | `app/services/` | Negocio compartido o transversal; integraciones externas (`ServiceClient`) |
| Models | `app/models/*_model.py` | SQL directo async vía `Database`, retornan dicts (errores: `ValueError`) |
| Database | `app/core/database.py` | Pool, conexiones cortas, traducción de errores |
| Esquema | `database/` | Tablas y stored procedures en SQL plano |

Cada capa recibe la anterior por constructor y se inyecta con `Depends`:

```
DatabaseDep → UserModelDep (get_user_model) → UserControllerDep → endpoint
```

Así cualquier capa se reemplaza en tests con `dependency_overrides` (sobre la sub-app, ver abajo).
Las reglas de qué capa puede importar cuál están en `CLAUDE.md` y las verifica `tests/test_architecture.py`.

---

## `main.py` — Punto de Entrada

`create_app()` construye la app raíz:

- **Lifespan**: inicia el cliente HTTP y verifica la BD. Cada paso es best-effort (si la BD no responde, la app arranca y `/ready` lo reporta). Al apagar cierra cliente HTTP → pool de la BD.
- **Middlewares transversales** (de afuera hacia adentro): `ContextMiddleware` → `LoggerMiddleware` (si `LOGGER_MIDDLEWARE_ENABLED`) → `CORSMiddleware` (si hay `CORS_ORIGINS`).
- **Handlers de error** (`register_exception_handlers`) y router de health.
- **Sub-app v1** montada en `/api/v1`, guardada en `app.state.versioned_apps["v1"]`.
- **Telemetría** OpenTelemetry nativa de FastAPI (`OTEL_ENABLED`), excluyendo `/health` y `/ready`. `telemetry_config()` vive en `app/core/versioned_app.py` y se aplica a la raíz y a cada sub-app.

La configuración sale del singleton `settings` (`from app.core.environment import settings`): `create_app()`, `create_versioned_app()` y `build_v1_router()` no reciben `settings`.

## `create_versioned_app()`

Cada versión es una sub-app con: docs propias (públicas, con HTTP Basic o deshabilitadas), `RequestSizeMiddleware` (`REQUEST_MAX_SIZE_MB`, sin overrides por ruta) y los mismos handlers de error. El rate limit global por IP lo aplica nginx (`limit_req`); la app solo limita por ruta con `rate_limit()`.

Starlette **no** ejecuta el lifespan de sub-apps montadas: todo recurso con ciclo de vida se inicia en el lifespan raíz. Los `dependency_overrides` son por app: en tests se aplican sobre `app.state.versioned_apps["v1"]`.

---

## Componentes

### `app/core/`

- **`environment.py`**: `Settings` con todas las variables tipadas y el singleton `settings` (única forma de acceso: `settings.DB_HOST`; campos en MAYÚSCULA = nombre de la variable, derivados en minúscula como `settings.is_production`). Valida la configuración de producción (y `DOCS_PASSWORD` en staging) al arrancar y, si es inválida, lanza `RuntimeError` con las variables por nombre, sin valores; `startup_warnings` es una propiedad calculada (incluye claves desconocidas del `.env`). `ENV_FILE` elige el `.env` (vacío = ninguno).
- **`database.py`**: un engine por proceso (creado en el primer uso, liberado con `dispose_engine()`), `Database` con `fetch_one`, `fetch_all`, `fetch_value`, `execute`, `transaction()`, `call_procedure()` y `ping()`, y `translate_db_error()` (1062 → 409, pool agotado → 503, timeout → 504, conexión perdida → 503, `SIGNAL` → 409).
- **`rate_limit.py`**: `rate_limit("5/minute")` como dependencia por ruta; `build_storage()` en memoria o Redis (redis-py), fail-open si Redis falla o está mal configurado.
- **`http_client.py`**: `ServiceClient`, base de toda integración externa: un pool httpx por servicio, reintentos solo idempotentes, `translate_http_error()` (503/504/502), `redact_url()`, `close_all()` en el lifespan. Ver [services](features/services.md).
- **`encryption.py`**: `encrypt()`, `decrypt()`, `rotate()` con MultiFernet (`ENCRYPTION_KEYS`); `fernet_key_from_secret()` para migrar datos de omnicanal. Ver [security](features/security.md).
- **`encoding.py`**: `encode_id()`, `decode_id()`, `EncodedId` (entrada) y `EncodedIdOut` (salida) con sqids (`ENCODING_ALPHABET`).
- **`logging_config.py`**: formato text o JSON (`JsonFormatter`), `request_id` en cada línea (`RequestContextFilter`) y `AsgiTracebackFilter` (descarta el traceback duplicado de uvicorn cuando el handler de 500 ya lo registró).
- **`context.py`**: `current_http_identifier`, `current_request_ip`, `current_request_method`, `current_request_route`, `current_request_host`, `current_request_user_agent`, `current_user_id`. Pensadas para auditoría (quién, desde dónde, en qué ruta); ver [Context](features/context.md).

### `database/` y `app/models/`

- `database/`: esquema en SQL plano. `init/NNN_descripcion.sql` se aplican en orden con el gestor de BD o el cliente `mariadb` (docker-compose arranca la base vacía; los tests los aplican solos al iniciar); `procedures/` guarda los stored procedures (ejemplo `sp_user_stats.sql`, se aplican igual). Ver [database/README.md](../database/README.md).
- `app/models/*_model.py`: clases `XxxModel(db: Database)` con métodos async y SQL parametrizado. Nunca devuelven un `Result` vivo, siempre dicts.

### `app/exceptions/`

`AppHttpException(message, status_code, context, *, code, reason, errors, public, headers)`. Todos los errores (handlers y middlewares) salen de `responses.py` con el formato `{"detail": {"msg", "type", "code?", "reason?", "errors?", "request_id", "context?", "loc?"}}`; `context` solo en development; `loc` (del traceback) solo en los 500 no controlados, en development.

### `app/routes/`

- `health.py`: `/health` y `/ready` en la app raíz (sin versión ni rate limit).
- `v1/routes.py`: `build_v1_router()` agrupa los routers; `test.py` solo se incluye si `APP_ENV != production`.

### `app/utils/`

`response.py`, `pagination.py`, `file_upload.py` (copia por bloques con `anyio`, valida tipo y tamaño), `passwords.py` (contraseñas cifradas reversibles sobre `core/encryption.py`), `dict_utils.py` (`sanitize()`, `is_sensitive_key()`), `validation_messages.py` (mensajes de validación en español, usados en los 422 y en los errores de configuración), `http.py` (`client_ip()`, `log_level_for_status()`, usados por middlewares, handlers y rate limit).

---

## Convenciones de Nombres

| Tipo | Archivo | Clase / variable |
|---|---|---|
| Tabla | `database/init/00N_posts.sql` | `posts` |
| Modelo SQL | `app/models/post_model.py` | `PostModel`, `PostModelDep` |
| Controlador | `app/controllers/post_controller.py` | `PostController`, `PostControllerDep` |
| Service | `app/services/payments_service.py` | `PaymentsService`, `PaymentsServiceDep` |
| Routes | `app/routes/v1/posts.py` | `router` |
| Schemas | `app/schemas/post.py` | `PostCreate`, `PostUpdate`, `PostOut` |
| Tests | `tests/test_posts_api.py` | `test_*` |

Clases en `PascalCase`, funciones y variables en `snake_case`.

---

## Reglas Importantes

1. Todo endpoint usa `response_model=ApiResponse[T]` y `success()` / `paginated()` / `empty()`.
2. Todo error controlado es `AppHttpException` (nunca `HTTPException`).
3. Todo el I/O es async; nada bloqueante dentro de `async def` ([best-practices](development/best-practices.md)).
4. SQL siempre con parámetros `:nombre`; columnas dinámicas solo desde whitelist.
5. Todo cambio de esquema es un script nuevo numerado en `database/init/` (nunca editar uno ya aplicado).
6. Toda variable de entorno nueva se declara en `Settings` (en su sección) y se documenta en `.env.example` (misma sección); `tests/test_environment.py` falla si falta una de las dos.
7. Los archivos en `uploads/` son temporales: eliminarlos siempre en `finally`.
