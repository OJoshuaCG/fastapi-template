# Arquitectura y estructura

Reglas de async, capas, sub-apps, estructura de carpetas y nombres. `tests/test_architecture.py` verifica las reglas de capas leyendo los imports (AST).

## Regla número uno: nada bloqueante dentro de `async def`

Un `async def` que llama algo síncrono (driver de BD síncrono, `requests`, `time.sleep`,
`open()` de archivos grandes, CPU pesado) **congela el worker entero**: ninguna otra request
—ni `/health`— se atiende mientras dura. Por eso:

- BD: siempre `await db.fetch_one(...)` etc. (`app/core/database.py`, driver asyncmy).
- HTTP saliente: un service que hereda de `ServiceClient` (`app/services/`). Nunca `requests`.
- Archivos: `anyio.Path` / `anyio.open_file`.
- CPU o librerías síncronas: `await anyio.to_thread.run_sync(fn, ...)`.
- `asyncio.create_task(...)`: guardar la referencia (Ruff RUF006 lo detecta).
- Ruff con reglas `ASYNC` detecta llamadas bloqueantes; pytest falla con corrutinas sin `await`.
- Para diagnosticar bloqueos: `PYTHONASYNCIODEBUG=1` en desarrollo, `py-spy dump` en producción
  (ver `docs/development/best-practices.md`).

## Arquitectura

**Routes → Controllers → (Services) → Models → Database**

```
routes ──► controllers ──┬──► services (negocio) ──┬──► models ──► core.database ──► MariaDB
                         │                         └──► services (integración) ──► APIs externas
                         ├──► services (integración)            (ServiceClient)
                         └──► models
schemas ◄── routes, controllers, services          Base: core · utils · exceptions ◄── cualquier capa
```

| Capa | Hace | Prohibido |
|---|---|---|
| **routes** | endpoint, schemas, `Depends`, llama **un** método del controller, `success/paginated/empty` | SQL, models, services, httpx, cifrar/hashear, negocio (excepción: `routes/v1/test.py`) |
| **controllers** | caso de uso: orquesta models y services, 404/409, transacción multi-model. Reciben **schemas** | SQL, httpx, `Request`/`Response`, `ApiResponse`, importar otro controller, transacción abierta durante HTTP |
| **services** | negocio compartido (≥2 controllers) o transversal (auditoría, notificaciones) · integraciones `XService(ServiceClient)` | `Request`/`Response`/`UploadFile`, importar controllers/routes, SQL (va en models), `httpx.AsyncClient` propio, devolver `httpx.Response` |
| **models** | SQL / SPs vía `Database` → `dict`/`list`/`int`/`None` | importar services/controllers/schemas, `AppHttpException` (lanzar `ValueError`) |
| **core · utils · exceptions** | infraestructura con estado · helpers sin estado · errores | negocio, importar capas superiores |

- Crear un **service** solo si: lo usan ≥2 controllers, es una integración externa, o es transversal.
  Si solo lo usa un controller, va en el controller.
- Todo se inyecta con `Depends` (`UserControllerDep`, `UserModelDep`, `HttpbinServiceDep`) y se reemplaza
  en tests con `dependency_overrides`.
- `tests/test_architecture.py` verifica parte de estas reglas leyendo los imports (AST): falla si una capa importa
  otra prohibida (incluidas routes → services, salvo `routes/v1/test.py`), si routes/controllers usan `httpx` o
  `sqlalchemy`, si alguien usa `requests`, si se crea `httpx.AsyncClient(` fuera de `core/http_client.py` o si un
  model lanza errores HTTP. También recorre las rutas registradas y falla si un `GET` de listado
  (`ApiResponse[list[...]]`) no recibe exactamente un `Annotated[XxxListQuery, Query()]` (contrato de la API). El resto
  (`Request`/`Response` fuera de routes, controller → controller, devolver `httpx.Response`) se cuida en revisión de código.
- **Esquema** (`database/`): tablas y stored procedures en SQL plano. No se usa ORM ni Alembic
  (Alembic es opcional: `uv add alembic` + pasos en `database/README.md`; `alembic.ini` ya está en la raíz).

### App raíz y sub-apps versionadas

```
main.py  create_app()
  ├── Middlewares raíz: ContextMiddleware → LoggerMiddleware → CORSMiddleware
  ├── Lifespan: verificación BD / cierre de clientes HTTP (close_all) + dispose del pool
  ├── Exception handlers (register_exception_handlers)
  ├── GET /health   liveness (no toca la BD)
  ├── GET /ready    readiness (SELECT 1, 503 si la BD no responde)
  └── /api/v1 → create_versioned_app("v1")
        ├── RequestSizeMiddleware (REQUEST_MAX_SIZE_MB)
        ├── Exception handlers
        └── docs propios: /api/v1/docs, /api/v1/redoc
```

- Lo transversal (request id, logging, CORS, recursos con ciclo de vida) vive en la **raíz**.
- La sub-app lleva rutas, documentación y límite de body de la versión.
- El rate limit global por IP lo aplica nginx (`limit_req`); la app solo limita por ruta (`rate_limit()`).
- Starlette **no ejecuta el lifespan de sub-apps montadas**: todo recurso se inicia en `main.py`.
- `dependency_overrides` son por app: en tests se aplican sobre `app.state.versioned_apps["v1"]`.

## Estructura

```
app/
├── core/
│   ├── environment.py       # Settings (pydantic-settings): TODAS las variables de entorno → `settings`
│   ├── database.py           # Engine async, Database (fetch_one/fetch_all/execute/...), errores BD
│   ├── rate_limit.py         # rate_limit("5/minute") como dependencia (librería limits)
│   ├── logging_config.py     # configure_logging(): text/json, request_id, filtros uvicorn
│   ├── context.py            # ContextVars de la request (request id, ip, user_id...)
│   ├── versioned_app.py      # create_versioned_app()
│   ├── http_client.py        # ServiceClient: base de integraciones externas (httpx)
│   ├── encryption.py         # encrypt/decrypt/rotate (MultiFernet, ENCRYPTION_KEYS)
│   ├── encoding.py           # encode_id/decode_id, EncodedId / EncodedIdOut (sqids)
│   └── sql_filters.py        # WhereBuilder / order_by: filtros y orden de listados a SQL
├── models/                   # *_model.py: SQL directo async
├── controllers/              # *_controller.py: casos de uso
├── services/                 # *_service.py: negocio compartido + integraciones externas
├── schemas/                  # Schemas Pydantic (entrada/salida)
├── routes/
│   ├── health.py             # /health, /ready (app raíz)
│   └── v1/                   # routes.py arma el router; test.py solo fuera de producción
├── middleware/               # ASGI puros: Context, Logger, RequestSize
├── exceptions/               # AppHttpException, handlers, serializador único de errores
└── utils/                    # response, list_query, file_upload, passwords, dict_utils,
                              # http, validation_messages (mensajes de validación en español)
database/                     # Esquema en SQL plano: init/NNN_*.sql (en orden), procedures/
tests/                        # pytest contra MariaDB real
main.py                       # create_app() + lifespan
```

## Nombres

- Tablas: `database/init/00N_posts.sql` → tabla `posts`
- Models SQL: `app/models/post_model.py` → `PostModel`, `PostModelDep`
- Controllers: `app/controllers/post_controller.py` → `PostController`, `PostControllerDep`
- Services: `app/services/payments_service.py` → `PaymentsService`, `PaymentsServiceDep`
- Routes: `app/routes/v1/posts.py` → `router`
- Schemas: `app/schemas/post.py` → `PostCreate`, `PostUpdate`, `PostOut`
- Tests: `tests/test_posts_api.py` → funciones `test_*`
- Clases `PascalCase`, funciones/variables `snake_case`.

