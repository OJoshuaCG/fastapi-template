# FastAPI Template

> **Plantilla FastAPI 100% async (MariaDB/MySQL) lista para producción: arquitectura MVC, API versionada por sub-apps, respuestas y errores estandarizados, rate limiting, observabilidad y despliegue con Docker + Nginx.**

## Características

| Categoría | Funcionalidad |
|---|---|
| **Arquitectura** | Routes → Controllers → Models → Database, inyección con `Depends`, API versionada por sub-apps |
| **Async** | SQLAlchemy 2.1 async + `asyncmy`, cliente `httpx` compartido, uploads con `anyio`, trabajo de CPU en threads |
| **Base de datos** | MariaDB / MySQL. SQL directo con `Database` (`fetch_one`, `fetch_all`, `execute`, `transaction`, `call_procedure`) |
| **Esquema** | SQL plano en `database/` (`init/NNN_*.sql` en orden + `procedures/`), sin ORM ni Alembic (Alembic opcional: `uv add alembic`, ver `database/README.md`). `001_users.sql` crea la tabla `users` |
| **Configuración** | `pydantic-settings` tipado y validado al arrancar (`app/core/environment.py` → `settings.DB_HOST`). `APP_ENV` obligatorio |
| **Respuestas** | Envelope `ApiResponse[T]` con `success()`, `paginated()`, `empty()` |
| **Errores** | `AppHttpException` + handlers globales con un único formato `{"detail": {...}}` y `request_id` |
| **Rate limiting** | Global por IP en nginx (`limit_req`) + dependencia `rate_limit()` por ruta (librería `limits`); memoria o Redis |
| **Middlewares** | ASGI puros: Context (Request ID), Logger, CORS, Request Size |
| **Observabilidad** | Logs text/JSON con Request ID, OpenTelemetry nativo de FastAPI |
| **Health** | `/health` (liveness) y `/ready` (readiness, 503 si la BD no responde) |
| **Calidad** | Tests con pytest contra MariaDB real, Ruff (incluye reglas `ASYNC`), pre-commit |
| **Despliegue** | Dockerfile multi-stage sin privilegios, compose con MariaDB (esquema inicial desde `database/init/`) + Nginx |

---

## Requisitos

- Python **3.13+** (`.python-version` fija 3.14)
- [uv](https://docs.astral.sh/uv/)
- MariaDB 10.6+/11 o MySQL 8 (o Docker para levantarla)

## Inicio Rápido

```bash
# 1. Dependencias (incluye el grupo dev: pytest, ruff, etc.)
uv sync

# 2. Entorno (APP_ENV es obligatorio: sin .env la app no arranca)
cp .env.example .env
#    editar DB_USER, DB_PASS, DB_NAME...

# 3. Esquema (una vez, con la BD ya creada)
mariadb -h localhost -u <user> -p <db> < database/init/001_users.sql
mariadb -h localhost -u <user> -p <db> < database/procedures/sp_user_stats.sql   # SP de ejemplo

# 4. Ejecutar
uv run fastapi dev        # desarrollo con reload (reiniciar si cambia .env)
uv run fastapi run        # modo producción local
```

| URL | Descripción |
|---|---|
| `http://localhost:8000/health` | Liveness (no toca la BD) |
| `http://localhost:8000/ready` | Readiness (verifica la BD, 503 si no responde) |
| `http://localhost:8000/api/v1/docs` | Swagger UI v1 |
| `http://localhost:8000/api/v1/redoc` | ReDoc v1 |
| `http://localhost:8000/api/v1/users` | CRUD de ejemplo |
| `http://localhost:8000/api/v1/test/ping` | Endpoints de ejemplo (no se registran en producción) |

Guía detallada: [docs/getting-started.md](docs/getting-started.md).

---

## Configuración

Todas las variables se declaran en `app/core/environment.py` (`from app.core.environment import settings`, luego `settings.DB_HOST`: mismo nombre que la variable) y se documentan en `.env.example`, en la misma sección. En `.env.example` van sin comentar las variables que se revisan en cada proyecto y entorno (cambian entre dev/staging/prod o deben coincidir con nginx, la BD o los workers); las opcionales van comentadas con su default seguro (`# VAR=default`). Una variable vacía (`VAR=`) usa el default. Las más importantes:

| Variable | Descripción |
|---|---|
| `APP_ENV` | **Obligatoria**: `development` \| `test` \| `staging` \| `production` |
| `SECRET_KEY` | Reservado para la auth del proyecto. En producción, mínimo 32 caracteres (la app no arranca si no) |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME` | Conexión MariaDB/MySQL |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, `DB_STATEMENT_TIMEOUT` | Pool y timeouts |
| `DOCS_ENABLED`, `DOCS_PASSWORD_ENABLED`, `DOCS_USER`, `DOCS_PASSWORD` | Docs (vacío = habilitadas fuera de producción) |
| `RATE_LIMIT_ENABLED`, `RATE_LIMIT_LOGIN`, `RATE_LIMIT_REDIS_ENABLED`, `RATE_LIMIT_REDIS_URL` | Rate limiting |
| `CORS_ORIGINS` | Orígenes separados por coma. Vacío = CORS deshabilitado. `*` prohibido en producción |
| `LOGGER_LEVEL`, `LOG_FORMAT`, `LOGGER_MIDDLEWARE_*`, `LOGGER_EXCEPTIONS_ENABLED` | Logging |
| `REQUEST_MAX_SIZE_MB`, `PAGINATION_MAX_SIZE`, `UPLOAD_DIR` | Límites y uploads |
| `HTTP_CLIENT_*`, `OTEL_ENABLED` | Cliente HTTP y observabilidad |
| `WORKERS` | Workers de uvicorn (lo usa el entrypoint de Docker) |
| `ENV_FILE` | Archivo `.env` a leer (default `.env` de la raíz; vacío = ninguno, como en los tests) |

En producción la configuración se valida al arrancar y falla rápido ante valores inseguros (`SECRET_KEY` corto, `DB_PASS` vacío o débil, `CORS_ORIGINS=*`). `DOCS_PASSWORD` débil (con docs protegidos) también falla en staging.

---

## Estructura

`app/` (core, models, controllers, routes, schemas, exceptions, middleware, utils), `database/` (esquema SQL), `tests/` y `docker/`. Árbol completo y responsabilidades por archivo: [docs/project-structure.md](docs/project-structure.md).

---

## Arquitectura

```
main.py (app raíz: lifespan, Context/Logger/CORS, handlers de error)
├── GET /health              ← liveness
├── GET /ready               ← readiness (BD)
└── /api/v1  → sub-app       ← create_versioned_app("v1"): docs,
    ├── /docs, /redoc           límite de body, handlers de error
    ├── /users                ← CRUD de ejemplo
    └── /test/...             ← solo fuera de producción
```

El lifespan de la app raíz inicia y cierra el cliente HTTP y el pool de la BD (Starlette no ejecuta el lifespan de sub-apps montadas).

### Agregar v2

```python
# main.py
v2 = create_versioned_app("v2")
v2.include_router(build_v2_router())
app.mount("/api/v2", v2)
```

---

## Patrones de Uso

### Endpoint completo (Routes → Controllers → Models)

```python
# app/routes/v1/users.py
@router.get("/{user_id}", response_model=ApiResponse[UserOut])
async def get_user(user_id: int, users: UserControllerDep):
    return success(data=await users.get_user(user_id))


@router.get("", response_model=ApiResponse[list[UserOut]])
async def list_users(users: UserControllerDep, pagination: PaginationDep):
    items, total = await users.list_users(pagination)
    return paginated(items, total=total, pagination=pagination)
```

```python
# app/models/user_model.py
class UserModel:
    def __init__(self, db: Database):
        self.db = db

    async def find_by_id(self, user_id: int) -> dict | None:
        return await self.db.fetch_one(
            "SELECT id, username, email FROM users WHERE id = :id", {"id": user_id}
        )
```

### Respuestas

```json
{"data": {"id": 1, "username": "john"}}
{"data": [...], "pagination": {"page": 1, "size": 20, "total": 150, "pages": 8, "has_next": true, "has_prev": false}}
{"message": "Usuario eliminado exitosamente"}
```

### Errores

```python
from app.exceptions import AppHttpException

raise AppHttpException("Usuario no encontrado", 404, {"user_id": user_id}, code="user_not_found")
```

```json
{"detail": {"msg": "Usuario no encontrado", "type": "NotFound", "code": "user_not_found", "request_id": "..."}}
```

`context` solo se incluye en `APP_ENV=development`; `loc` (archivo/función/línea) solo en los 500 no controlados, también solo en development. Los errores de BD se traducen solos: duplicado → 409, pool agotado → 503, timeout de sentencia → 504.

### Rate limiting por ruta

```python
from app.core.rate_limit import rate_limit

@router.post("/login", dependencies=[rate_limit("5/minute")])
async def login(...): ...
```

Responde 429 con header `Retry-After`. El límite global por IP lo aplica nginx (`limit_req`).

### Servicios externos

Cada API externa es un service que hereda de `ServiceClient` (pool propio, timeouts, reintentos seguros,
`X-Request-ID` y errores traducidos a 502/503/504):

```python
class PaymentsService(ServiceClient):
    name = "payments"
    base_url = "https://api.payments.example/v1"

    async def get_order(self, order_id: str) -> dict:
        return await self.get_json(f"/orders/{order_id}")

PaymentsServiceDep = Annotated[PaymentsService, Depends(PaymentsService.instance)]
```

Ejemplo completo: `app/services/httpbin_service.py`. Guía: [docs/features/services.md](docs/features/services.md).

### Seguridad

Cifrado reversible con rotación de llaves (`app/core/encryption.py`, `ENCRYPTION_KEYS`), contraseñas cifradas
(auditables) y encoding de IDs públicos (`app/core/encoding.py`, sqids): [docs/features/security.md](docs/features/security.md).

Trabajo de CPU o librerías síncronas: `await anyio.to_thread.run_sync(func, ...)`. Reglas completas en [docs/development/best-practices.md](docs/development/best-practices.md).

---

## Tests y calidad

```bash
docker compose -f docker-compose.test.yml up -d --wait   # MariaDB de test (puerto 3307, en RAM)
uv run pytest                                            # tests con BD se omiten si no hay MariaDB
docker compose -f docker-compose.test.yml down

uv run ruff check .
uv run ruff format .

uv run --with pre-commit pre-commit install              # ruff + detect-secrets en cada commit
```

En pytest, cualquier `DeprecationWarning` (incluidas las de FastAPI, Starlette y uvicorn) y `RuntimeWarning` es un error.

---

## Docker

```bash
cp .env.example .env     # APP_ENV=production, SECRET_KEY, DB_USER, DB_PASS...
docker compose up -d --build
```

Servicios: `db` (MariaDB 11, arranca **vacía**: aplicar `database/init/*.sql` y `database/procedures/*.sql` con el gestor de BD, ver [database/README.md](database/README.md)) → `api` → `nginx`. Ver [docs/docker-deployment.md](docs/docker-deployment.md).

---

## Comandos de Referencia

```bash
# Desarrollo
uv run fastapi dev
uv run fastapi dev --host 0.0.0.0 --port 8080

# Dependencias
uv add <paquete>
uv add --group dev <paquete>
uv sync --extra redis          # rate limit compartido en Redis

# Esquema: cambios nuevos = script numerado nuevo en database/init/
mariadb -h <host> -u <user> -p <db> < database/init/002_descripcion.sql
```

---

## Documentación

- [Inicio Rápido](docs/getting-started.md)
- [Estructura del Proyecto](docs/project-structure.md)
- [Mejores Prácticas (async)](docs/development/best-practices.md)
- [API Versionada](docs/features/api-versioning.md)
- [Respuestas Estándar](docs/features/response-format.md)
- [Paginación](docs/features/pagination.md)
- [File Upload](docs/features/file-upload.md)
- [Rate Limiting](docs/features/rate-limiting.md)
- [CORS](docs/features/cors.md)
- [Middlewares](docs/features/middlewares.md)
- [Context](docs/features/context.md)
- [Logging](docs/features/logging.md)
- [Excepciones](docs/features/exceptions.md)
- [Base de Datos](docs/features/database.md)
- [Esquema de BD](database/README.md)
- [Despliegue](docs/deployment.md) · [Docker](docs/docker-deployment.md)

## Tecnologías

- **[FastAPI](https://fastapi.tiangolo.com/)** 0.142 + **Starlette** 1.7
- **[SQLAlchemy 2.1](https://docs.sqlalchemy.org/)** (async) + **asyncmy**
- **[Pydantic v2](https://docs.pydantic.dev/)** + **pydantic-settings**
- **[limits](https://limits.readthedocs.io/)** — rate limiting async
- **[httpx](https://www.python-httpx.org/)** — cliente HTTP async
- **[uv](https://docs.astral.sh/uv/)** y **[Ruff](https://docs.astral.sh/ruff/)**
