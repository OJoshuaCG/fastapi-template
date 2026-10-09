# FastAPI Template

> **Plantilla FastAPI 100% async (MariaDB/MySQL) lista para producción: arquitectura MVC, API versionada por sub-apps, respuestas y errores estandarizados, rate limiting, observabilidad y despliegue con Docker + Nginx.**

## Características

| Categoría | Funcionalidad |
|---|---|
| **Arquitectura** | Routes → Controllers → (Services) → Models → Database, inyección con `Depends`, API versionada por sub-apps |
| **Async** | SQLAlchemy 2.1 async (solo engine/pool) + `asyncmy`, un pool `httpx` por servicio externo (`ServiceClient`), uploads con `anyio`, trabajo de CPU en threads |
| **Base de datos** | MariaDB / MySQL. SQL directo con `Database` (`fetch_one`, `fetch_all`, `execute`, `transaction`, `call_procedure`) |
| **Esquema** | SQL plano en `database/` (`init/NNN_*.sql` en orden + `procedures/`), sin ORM ni Alembic (Alembic opcional: `uv add alembic`, ver `database/README.md`). `001_users.sql` crea la tabla `users` |
| **Configuración** | `pydantic-settings` tipado y validado al arrancar (`app/core/environment.py` → `settings.DB_HOST`). `APP_ENV` obligatorio |
| **Respuestas** | Envelope `ApiResponse[T]` con `success()`, `paginated()`, `empty()` |
| **Listados** | Contrato único: `page`/`size`, `sort=-campo`, filtros (`_from`/`_to`, `_min`/`_max`, `q`, IN) y 422 ante parámetros desconocidos (`ListQuery` + `WhereBuilder`) |
| **Errores** | `AppHttpException` + handlers globales con un único formato `{"detail": {...}}` y `request_id` |
| **Rate limiting** | Global por IP en nginx (`limit_req`) + dependencia `rate_limit()` por ruta (librería `limits`); memoria o Redis |
| **Middlewares** | ASGI puros: Context (Request ID), Logger, CORS, Request Size |
| **Observabilidad** | Logs text/JSON con Request ID, OpenTelemetry nativo de FastAPI |
| **Health** | `/health` (liveness) y `/ready` (readiness, 503 si la BD no responde) |
| **Seguridad** | Cifrado con rotación de llaves (`ENCRYPTION_KEYS`), IDs públicos codificados (sqids), validación de configuración insegura al arrancar |
| **Calidad** | Tests con pytest contra MariaDB real, cobertura (`pytest-cov`), Ruff (incluye reglas `ASYNC`), pyright, pip-audit, pre-commit |
| **Despliegue** | Dockerfile multi-stage sin privilegios, compose con MariaDB (arranca vacía; el esquema de `database/` se aplica a mano) + Nginx |

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
| `APP_NAME` | Nombre de la app (título en los docs) |
| `SECRET_KEY` | Reservado para la auth del proyecto. En producción, mínimo 32 caracteres (la app no arranca si no) |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_COLLATION` | Conexión MariaDB/MySQL |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, `DB_CONNECT_TIMEOUT`, `DB_STATEMENT_TIMEOUT` | Pool y timeouts |
| `ENCRYPTION_KEYS` | Llaves de cifrado (la primera cifra, todas descifran). Obligatoria en staging y producción |
| `ENCODING_ALPHABET`, `ENCODING_MIN_LENGTH` | Encoding de IDs públicos. Alfabeto propio y fijo por proyecto (el default falla en producción) |
| `DOCS_ENABLED`, `DOCS_PASSWORD_ENABLED`, `DOCS_USER`, `DOCS_PASSWORD` | Docs (vacío = habilitadas fuera de producción) |
| `RATE_LIMIT_ENABLED`, `RATE_LIMIT_LOGIN`, `RATE_LIMIT_REDIS_ENABLED`, `RATE_LIMIT_REDIS_URL` | Rate limiting |
| `CORS_ORIGINS`, `CORS_ALLOW_CREDENTIALS` | Orígenes separados por coma. Vacío = CORS deshabilitado. `*` prohibido en producción |
| `LOGGER_LEVEL`, `LOG_FORMAT`, `LOGGER_MIDDLEWARE_*`, `LOGGER_EXCEPTIONS_ENABLED` | Logging |
| `REQUEST_MAX_SIZE_MB`, `PAGINATION_MAX_SIZE`, `UPLOAD_DIR` | Límites y uploads |
| `HTTP_CLIENT_*`, `OTEL_ENABLED` | Cliente HTTP y observabilidad |
| `WORKERS` | Workers de uvicorn (lo usa el entrypoint de Docker) |
| `ENV_FILE` | Archivo `.env` a leer (default `.env` de la raíz; vacío = ninguno, como en los tests) |

La configuración se valida al arrancar y falla rápido ante valores inseguros en staging y producción. Lista completa de validaciones y cómo agregar una variable: [docs/development/configuration.md](docs/development/configuration.md).

---

## Estructura

`app/` (core, models, controllers, services, routes, schemas, exceptions, middleware, utils), `database/` (esquema SQL), `tests/` y `docker/`. Árbol completo y responsabilidades por archivo: [docs/project-structure.md](docs/project-structure.md).

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

El lifespan de la app raíz verifica la BD al arrancar y, al apagar, cierra los clientes HTTP (`close_all`) y el pool de la BD; los clientes HTTP se crean en el primer uso. Starlette no ejecuta el lifespan de sub-apps montadas.

### Agregar v2

```python
# main.py
v2 = create_versioned_app("v2")
v2.include_router(build_v2_router())
app.mount("/api/v2", v2)
```

---

## Patrones de Uso

| Necesito… | Cómo | Guía |
|---|---|---|
| Crear una feature (tabla → route → test) | Receta paso a paso con el ejemplo `users` | [new-feature.md](docs/development/new-feature.md) |
| Diseñar un endpoint | Contrato: path, query, body, filtros, fechas, orden, status | [api-contract.md](docs/development/api-contract.md) |
| Listar con filtros y orden | Modelo que hereda de `ListQuery` + `WhereBuilder`/`order_by` en el model | [pagination](docs/features/pagination.md) |
| Responder | `ApiResponse[T]` con `success()`, `paginated()`, `empty()` | [response-format](docs/features/response-format.md) |
| Lanzar un error | `AppHttpException(msg, status, context, code=...)` → `{"detail": {...}}` | [exceptions](docs/features/exceptions.md) |
| Consultar la BD | `await db.fetch_one/fetch_all/execute`, SQL directo con parámetros | [data-access.md](docs/development/data-access.md) |
| Llamar una API externa | Un service que hereda de `ServiceClient` | [external-services.md](docs/development/external-services.md) |
| Limitar una ruta | `dependencies=[rate_limit("5/minute")]` → 429 con `Retry-After` | [rate-limiting](docs/features/rate-limiting.md) |
| Cifrar datos o exponer IDs | `encrypt()`/`decrypt()`, `EncodedId`/`EncodedIdOut` | [security](docs/features/security.md) |
| Trabajo de CPU o librerías síncronas | `await anyio.to_thread.run_sync(func, ...)` | [best-practices](docs/development/best-practices.md) |

Reglas de programación completas: [docs/development/](docs/development/README.md). Ejemplo de referencia: `users`
(`app/models/user_model.py`, `app/controllers/user_controller.py`, `app/routes/v1/users.py`).

---

## Tests y calidad

```bash
docker compose -f docker-compose.test.yml up -d --wait   # MariaDB de test (puerto 3307, en RAM)
uv run pytest                                            # tests con BD se omiten si no hay MariaDB
docker compose -f docker-compose.test.yml down

uv run ruff check . && uv run ruff format --check .      # lint y formato (sin reescribir)
uv run pyright                                           # tipos (Ruff no verifica tipos)
uv run pytest --cov                                      # cobertura de app/ (se mide, sin umbral)
uv run pip-audit                                         # vulnerabilidades en dependencias

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

- [Inicio Rápido](docs/getting-started.md) · [Iniciar un proyecto desde la plantilla](docs/development/starting-new-project.md)
- [Estructura del Proyecto](docs/project-structure.md)
- [Reglas de programación](docs/development/README.md) · [Mejores Prácticas (async)](docs/development/best-practices.md)
- [Guía para agentes de IA](AGENTS.md)
- [API Versionada](docs/features/api-versioning.md)
- [Respuestas Estándar](docs/features/response-format.md)
- [Contrato de la API](docs/development/api-contract.md) · [Paginación, filtros y orden](docs/features/pagination.md)
- [File Upload](docs/features/file-upload.md)
- [Rate Limiting](docs/features/rate-limiting.md)
- [CORS](docs/features/cors.md)
- [Middlewares](docs/features/middlewares.md)
- [Context](docs/features/context.md)
- [Logging](docs/features/logging.md)
- [Excepciones](docs/features/exceptions.md)
- [Base de Datos](docs/features/database.md)
- [Servicios externos](docs/features/services.md)
- [Seguridad](docs/features/security.md)
- [Esquema de BD](database/README.md)
- [Despliegue](docs/deployment.md) · [Docker](docs/docker-deployment.md)

## Tecnologías

- **[FastAPI](https://fastapi.tiangolo.com/)** 0.142 + **Starlette** 1.7
- **[SQLAlchemy 2.1](https://docs.sqlalchemy.org/)** (async) + **asyncmy**
- **[Pydantic v2](https://docs.pydantic.dev/)** + **pydantic-settings**
- **[limits](https://limits.readthedocs.io/)** — rate limiting async
- **[httpx](https://www.python-httpx.org/)** — cliente HTTP async
- **[cryptography](https://cryptography.io/)** (Fernet) y **[sqids](https://sqids.org/)** — cifrado e IDs públicos
- **[uv](https://docs.astral.sh/uv/)**, **[Ruff](https://docs.astral.sh/ruff/)** y **[pyright](https://microsoft.github.io/pyright/)**
- **[pytest](https://docs.pytest.org/)** + pytest-asyncio, pytest-cov y **[pip-audit](https://pypi.org/project/pip-audit/)**
