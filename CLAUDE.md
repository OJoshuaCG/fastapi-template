# FastAPI Template - Guía para Agentes de IA

Plantilla base para nuevos proyectos FastAPI: **async de punta a punta**, MariaDB/MySQL,
sub-apps versionadas, formato de respuesta y de error estándar, tests contra BD real.

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
- `tests/test_architecture.py` verifica estas reglas leyendo los imports (AST): falla si una capa importa
  otra prohibida, si se crea `httpx.AsyncClient(` fuera de `core/http_client.py` o si un model lanza errores HTTP.
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
│   └── encoding.py           # encode_id/decode_id, EncodedId / EncodedIdOut (sqids)
├── models/                   # *_model.py: SQL directo async
├── controllers/              # *_controller.py: casos de uso
├── services/                 # *_service.py: negocio compartido + integraciones externas
├── schemas/                  # Schemas Pydantic (entrada/salida)
├── routes/
│   ├── health.py             # /health, /ready (app raíz)
│   └── v1/                   # routes.py arma el router; test.py solo fuera de producción
├── middleware/               # ASGI puros: Context, Logger, RequestSize
├── exceptions/               # AppHttpException, handlers, serializador único de errores
└── utils/                    # response, pagination, file_upload, passwords, dict_utils,
                              # http, validation_messages (mensajes de validación en español)
database/                     # Esquema en SQL plano: init/NNN_*.sql (en orden), procedures/
tests/                        # pytest contra MariaDB real
main.py                       # create_app() + lifespan
```

## Configuración (`app/core/environment.py`)

```python
from app.core.environment import settings

settings.DB_HOST                      # MAYÚSCULA = variable de entorno (mismo nombre que en .env)
settings.DB_PASS.get_secret_value()   # secretos (SecretStr): SECRET_KEY, DB_PASS, ENCRYPTION_KEYS, DOCS_PASSWORD...
settings.is_production                # minúscula = valor derivado (property)
```

- Una sola forma de acceso: el singleton `settings` del módulo (no hay `get_settings()` ni `SettingsDep`).
  `create_app()`, `create_versioned_app()` y `build_v1_router()` no reciben `settings`: lo importan.
- Campos en MAYÚSCULA idénticos a la variable de entorno. Derivados en minúscula (properties, siempre
  calculados): `is_production`, `is_development`, `is_deployed`, `docs_enabled`, `cors_allow_credentials`,
  `request_max_bytes`, `startup_warnings`.
- Leer `settings.X` **dentro de la función**, no copiarlo a constantes de módulo (los tests no podrían
  cambiarlo). Excepción: valores que forman parte del esquema OpenAPI, marcados `# leído al importar`
  (`PAGINATION_MAX_SIZE` en `app/utils/pagination.py`, `RATE_LIMIT_LOGIN` en `app/routes/v1/test.py`).
- `APP_ENV` es obligatorio (`development | test | staging | production`).
- Variable vacía en el `.env` (`DOCS_ENABLED=`) = usar el default (`env_ignore_empty=True`).
- Configuración inválida → la app no arranca: `RuntimeError` que lista las variables con error **por nombre**,
  en español, sin mostrar nunca los valores (`hide_input_in_errors=True`).
- En producción falla al arrancar con: `SECRET_KEY` < 32 caracteres, `DB_PASS` débil, `CORS_ORIGINS=*`,
  `ENCODING_ALPHABET` por defecto, o secretos repetidos (`SECRET_KEY`/`DB_PASS`/`ENCRYPTION_KEYS`).
  En staging y producción (`is_deployed`) también sin `ENCRYPTION_KEYS` o con `DOCS_PASSWORD` débil si los
  docs están protegidos. `ENCRYPTION_KEYS` inválida falla en cualquier entorno. Docs deshabilitados por
  defecto en producción.
- **Un secreto por propósito**: `SECRET_KEY` (auth del proyecto), `ENCRYPTION_KEYS` (cifrado), `ENCODING_ALPHABET`
  (IDs públicos), `DB_PASS`. Nunca derivar uno de otro ni reutilizar `SECRET_KEY` para cifrar.
- Integraciones externas: solo credenciales al env, con prefijo por servicio (`<NAME>_TOKEN`, `SecretStr`).
  La URL base va fija en el service; `<NAME>_BASE_URL` solo si cambia entre entornos (sandbox/producción).
- `SECRET_KEY` queda reservado para la auth del proyecto (el template aún no lo usa), pero se valida en producción.
- `ENV_FILE` elige el archivo `.env` a leer (vacío = ninguno; los tests lo dejan vacío para que el `.env`
  del desarrollador no les afecte). `extra="ignore"`: el `.env` también trae variables de infraestructura
  (`INFRA_ONLY_VARS` = `WORKERS`, `ENV_FILE`). `startup_warnings` (se loguea al arrancar)
  avisa además de claves desconocidas en el `.env` (typos como `DB_PASWORD`).
- `.env.example`: sin comentar = **revisar en cada proyecto/entorno** (cambian entre dev/staging/prod o deben coincidir con nginx/BD/workers); comentadas = **opcionales** con default seguro (`# VAR=default`).

**Agregar una variable** (2 pasos; `tests/test_environment.py` falla si falta uno):

1. Campo en `Settings`, en su sección, con tipo y default seguro (sin default = obligatoria).
2. La misma variable en `.env.example`, en la misma sección, con un comentario de una línea.

`tests/test_environment.py` verifica que `Settings` y `.env.example` estén sincronizados, que `.env.example`
cargue tal cual, que los secretos no se filtren (repr, dump, errores) y, por AST, que todo `settings.X` usado
exista y que el código de la app nunca asigne `settings`.

En tests:

```python
monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)   # se revierte solo
Settings(_env_file=None, APP_ENV="production", ...)          # tests de validación (tests/test_settings.py)
```

Nunca `cache_clear()` ni reasignar el módulo o el singleton.

## Base de datos (`app/core/database.py`)

API única de acceso a datos (SQL directo, async):

```python
from app.core.database import Database, DatabaseDep

row   = await db.fetch_one("SELECT ... WHERE id = :id", {"id": 1})   # dict | None
rows  = await db.fetch_all("SELECT ...", {...})                      # list[dict]
total = await db.fetch_value("SELECT COUNT(*) FROM posts")           # escalar
res   = await db.execute("INSERT ...", {...})                        # ExecResult(rowcount, lastrowid)
sets  = await db.call_procedure("sp_name", [arg1, arg2])             # list[list[dict]]

async with db.transaction() as tx:                                   # varias sentencias atómicas
    await db.execute("UPDATE ...", {...}, conn=tx)
    await db.execute("INSERT ...", {...}, conn=tx)
```

Reglas (derivadas de incidentes reales en omnicanal-api):

1. Un engine/pool por worker, creado en el primer uso y cerrado en el lifespan (`dispose_engine`).
   Nunca crear engines por request ni por instancia.
2. Cada helper es una unidad de trabajo corta: toma una conexión, ejecuta, materializa a dict y la
   devuelve al pool. Lecturas sin commit; escrituras con commit automático.
3. No mantener una conexión/transacción abierta mientras se espera I/O externa (HTTP, colas).
4. No usar `asyncio.gather` sobre la misma `tx`. Consultas independientes sin `conn=` sí pueden ir en paralelo.
5. Stored procedures: `call_procedure` drena todos los result sets y cierra el cursor siempre.
   Si falla, el contexto del error solo lleva `{"count": N}` de los parámetros (nunca sus valores).
   Ejemplo: `database/procedures/sp_user_stats.sql` (`DELIMITER`, 2 result sets, `SIGNAL`).
6. Pool: `DB_POOL_TIMEOUT=3` (fallar rápido con 503), `DB_POOL_RECYCLE=180` (< `wait_timeout`),
   `pre_ping`. Dimensionar: `WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW) × réplicas < max_connections`.
7. `DB_STATEMENT_TIMEOUT` corta consultas largas en el servidor (MariaDB `max_statement_time`, no aplica en SP).

Errores de BD traducidos automáticamente a `AppHttpException`:

| Situación | Status | code / reason |
|---|---|---|
| Pool agotado | 503 + Retry-After | `db_unavailable` / `pool_exhausted` |
| Conexión perdida | 503 + Retry-After | `db_unavailable` / `connection_lost` |
| Statement timeout | 504 | `db_timeout` / `statement_timeout` |
| `SIGNAL SQLSTATE '45000'` en SP | 409 (mensaje del SP) | `business_rule` |
| Clave duplicada | 409 | `conflict` / `duplicate` |
| FK / integridad | 409 | `conflict` / `integrity` |
| Otro | 500 | `db_error` |

Los mensajes de `SIGNAL` llegan al cliente: escribirlos aptos para usuario final.

## Crear una feature (receta completa)

### 1. Tabla (`database/init/00N_posts.sql`)

Script nuevo con el siguiente número libre. Nunca modificar un script ya aplicado en otro entorno.

```sql
CREATE TABLE IF NOT EXISTS posts (
    id         INT          NOT NULL AUTO_INCREMENT,
    title      VARCHAR(200) NOT NULL,
    content    TEXT         NULL,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

Aplicarlo con el gestor de BD, el cliente `mariadb` o por el DBA:

```bash
mariadb -h <host> -u <user> -p <db> < database/init/00N_posts.sql
```

Los tests borran todas las tablas y aplican `database/init/*.sql` + `database/procedures/*.sql` solos
(fixture `database_schema`, `sql_statements()` entiende `DELIMITER`). Stored procedures en
`database/procedures/`. Con docker-compose la BD arranca vacía: cada desarrollador aplica `database/init/*.sql`
y `database/procedures/*.sql` con su gestor de BD o el cliente `mariadb` (con `DB_USER`/`DB_PASS`);
ver `database/README.md`.

### 2. Model (`app/models/post_model.py`)

```python
from typing import Annotated, Any
from fastapi import Depends
from app.core.database import Database, DatabaseDep

_UPDATABLE = frozenset({"title", "content"})   # whitelist si se arman columnas dinámicas

class PostModel:
    def __init__(self, db: Database):
        self.db = db

    async def find_by_id(self, post_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM posts WHERE id = :id", {"id": post_id})

    async def find_all(self, *, limit: int, offset: int) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT * FROM posts ORDER BY id DESC LIMIT :limit OFFSET :offset",
            {"limit": limit, "offset": offset},
        )

    async def count(self) -> int:
        return int(await self.db.fetch_value("SELECT COUNT(*) FROM posts") or 0)

    async def create(self, data: dict[str, Any]) -> int:
        result = await self.db.execute(
            "INSERT INTO posts (title, content) VALUES (:title, :content)", data
        )
        return int(result.lastrowid or 0)

def get_post_model(db: DatabaseDep) -> PostModel:
    return PostModel(db)

PostModelDep = Annotated[PostModel, Depends(get_post_model)]
```

### 3. Controller (`app/controllers/post_controller.py`)

Recibe los **schemas** de la route (no dicts armados por ella) y decide cómo persistirlos.

```python
class PostController:
    def __init__(self, posts: PostModel):
        self.posts = posts

    async def get_post(self, post_id: int) -> dict:
        post = await self.posts.find_by_id(post_id)
        if not post:
            raise AppHttpException("Post no encontrado", 404, {"post_id": post_id}, code="post_not_found")
        return post

    async def list_posts(self, pagination: PaginationParams) -> tuple[list[dict], int]:
        items = await self.posts.find_all(limit=pagination.size, offset=pagination.offset)
        return items, await self.posts.count()

    async def create_post(self, payload: PostCreate) -> dict:
        post_id = await self.posts.create(payload.model_dump())
        return await self.get_post(post_id)

def get_post_controller(posts: PostModelDep) -> PostController:
    return PostController(posts)

PostControllerDep = Annotated[PostController, Depends(get_post_controller)]
```

No hacer "SELECT para ver si existe" antes de un INSERT: tiene carrera. El índice UNIQUE decide y
la capa de datos lanza 409 (`reason == "duplicate"`); el controller puede re-mapear el mensaje.

### 4. Schemas (`app/schemas/post.py`)

```python
class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    content: str | None = None

class PostOut(BaseModel):
    id: EncodedIdOut          # el int de la BD sale como string público ("Xk3pQ9aL")
    title: str
    content: str | None
    created_at: datetime
```

### 5. Routes (`app/routes/v1/posts.py`) y registro en `app/routes/v1/routes.py`

```python
router = APIRouter(prefix="/posts", tags=["Posts"])

@router.get("", response_model=ApiResponse[list[PostOut]])
async def list_posts(posts: PostControllerDep, pagination: PaginationDep):
    items, total = await posts.list_posts(pagination)
    return paginated(items, total=total, pagination=pagination)

@router.get("/{post_id}", response_model=ApiResponse[PostOut])
async def get_post(post_id: EncodedId, posts: PostControllerDep):   # llega como int; inválido → 404
    return success(data=await posts.get_post(post_id))

@router.post("", response_model=ApiResponse[PostOut], status_code=status.HTTP_201_CREATED)
async def create_post(payload: PostCreate, posts: PostControllerDep):
    return success(data=await posts.create_post(payload), message="Post creado")
```

```python
# app/routes/v1/routes.py → build_v1_router()
router.include_router(posts.router)
```

### 6. Test (`tests/test_posts_api.py`)

```python
pytestmark = pytest.mark.db

async def test_get_post_404(client: httpx2.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/posts/{encode_id(999999)}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "post_not_found"
```

Ejemplo completo de referencia: `users` (`app/models/user_model.py`, `app/controllers/user_controller.py`,
`app/routes/v1/users.py`, `tests/test_users_api.py`).

## Integraciones externas (`app/services/` + `ServiceClient`)

Cada API externa = un service. Ejemplo de referencia: `app/services/httpbin_service.py` (borrar al iniciar).

```python
# 1. app/core/environment.py + .env.example: PAYMENTS_TOKEN (SecretStr)
# 2. app/services/payments_service.py
class PaymentsService(ServiceClient):
    name = "payments"          # aparece en logs y en los mensajes de error
    base_url = "https://api.payments.example/v1"   # fija; property con settings solo si cambia por entorno
    timeout = 15               # opcional (default HTTP_CLIENT_TIMEOUT)

    def headers(self) -> dict[str, str]:       # por request: un token rotado aplica sin reiniciar
        return {"Authorization": f"Bearer {settings.PAYMENTS_TOKEN.get_secret_value()}"}

    async def get_order(self, order_id: str) -> dict:          # métodos de negocio, nunca httpx.Response
        return await self.get_json(f"/orders/{order_id}")

    async def find_order(self, order_id: str) -> dict | None:  # 404 esperado → None
        response = await self.request("GET", f"/orders/{order_id}", allow={404})
        return None if response.status_code == 404 else response.json()

PaymentsServiceDep = Annotated[PaymentsService, Depends(PaymentsService.instance)]

# 3. El controller lo recibe por constructor (get_x_controller(..., payments: PaymentsServiceDep))
```

La base ya resuelve (no reimplementar): pool httpx **por servicio** (perezoso, cerrado en el lifespan con
`close_all()`), timeouts de conexión/total/pool, sin seguir redirects, `X-Request-ID` propagado, reintentos
con backoff **solo** en GET/HEAD/OPTIONS/PUT/DELETE (`retry=True` para un POST con idempotency key),
`Retry-After` ≤ 5s, logs por intento sin query string ni bodies. Errores traducidos:

| Situación | Status | code / reason |
|---|---|---|
| Pool del servicio lleno | 503 | `external_service_unavailable` / `pool_exhausted` |
| No conecta / conexión cortada | 503 | `external_service_unavailable` / `connection_error` |
| Timeout | 504 | `external_service_timeout` / `timeout` |
| Proveedor responde 429/503 | 503 (+ su `Retry-After`) | `external_service_unavailable` / `upstream_429` |
| Proveedor responde 401/403 | 502 (**nunca** se reenvía el 401) | `external_service_error` / `upstream_auth` |
| Otro 4xx/5xx, redirect, JSON inválido | 502 | `external_service_error` / `upstream_<status>` / `invalid_json` |

**Prohibido**: `httpx.AsyncClient(...)` fuera de `core/http_client.py` (lo verifica `test_architecture.py`),
`requests`, llamar un servicio externo con una transacción de BD abierta, reenviar al cliente el status o body
del proveedor, poner tokens en la query string si el proveedor acepta headers.

Tests sin red: `PaymentsService(transport=httpx.MockTransport(handler))` y
`v1_app.dependency_overrides[PaymentsService.instance] = lambda: fake` (ver `tests/test_http_client.py`).

## Seguridad: cifrado, contraseñas y encoding de IDs

```python
from app.core.encryption import encrypt, decrypt, rotate, DecryptionError   # datos sensibles reversibles
from app.utils.passwords import encrypt_password, verify_password, reveal_password
from app.core.encoding import EncodedId, EncodedIdOut, encode_id, decode_id
```

- **Cifrado** (`ENCRYPTION_KEYS`, MultiFernet): la primera llave cifra, todas descifran. Rotar = nueva llave
  al inicio → `rotate(token)` → quitar la vieja. `DecryptionError` nunca incluye el token. Sin la variable
  (solo dev/test) se usa una llave temporal y se avisa al arrancar. Datos de omnicanal: agregar
  `fernet_key_from_secret(<su SECRET_KEY>)` al final de `ENCRYPTION_KEYS` y re-cifrar con `rotate()`.
- **Contraseñas: cifrado reversible** (decisión del equipo, para auditar). El controller cifra
  (`encrypt_password`), el login compara con `verify_password(pw, stored_or_None)` (nunca lanza; `None` =
  usuario inexistente). `reveal_password()` solo para auditoría/soporte: nunca en respuestas ni logs.
  Riesgo: BD + `ENCRYPTION_KEYS` = todas las contraseñas → la llave vive fuera de la BD y se respalda aparte.
  Columna `VARCHAR(512)`; `max_length=128` en el schema.
- **Encoding de IDs** (`app/core/encoding.py`, sqids, `ENCODING_ALPHABET` propio y fijo por proyecto): `EncodedId` en la **entrada**
  (path/query/body: solo acepta el string; inválido en la URL → 404, en el body → 422) y `EncodedIdOut` en
  la **salida** (el int del model se serializa como string). Es ofuscación, no autorización: validar acceso igual.

Detalle: `docs/features/services.md` y `docs/features/security.md`.

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

- **Paginación**: `PaginationDep` → `?page=1&size=20` (`pagination.size`, `pagination.offset`; `page` ≤ 1 000 000).
- **Uploads**: `await save_upload(file, allowed_types=[...], max_size_mb=2)` guarda por bloques;
  procesar y **siempre** `await anyio.Path(info["path"]).unlink(missing_ok=True)` en `finally`.
- **Límite de body**: `REQUEST_MAX_SIZE_MB` para toda la versión (igual a `client_max_body_size` de nginx;
  sin overrides por ruta). Para archivos más grandes, subir ambos.
- **ContextVars** (auditoría: quién/desde dónde/qué ruta): `from app.core.context import current_http_identifier,
  current_request_ip, current_user_id` (la capa de auth del proyecto debe hacer `current_user_id.set(...)`).

## Seguridad SQL

```python
# ✅ Siempre parámetros
await db.fetch_one("SELECT * FROM users WHERE id = :id", {"id": user_id})

# ❌ Nunca interpolar valores (SQL injection)
await db.fetch_one(f"SELECT * FROM users WHERE id = {user_id}")
```

Si hay que interpolar nombres de columna (UPDATE dinámico, ORDER BY), validarlos contra una whitelist
(ver `UserModel.update`).

## Tests

```bash
docker compose -f docker-compose.test.yml up -d --wait   # MariaDB en RAM, puerto 3307
uv run pytest                                            # los tests @db se saltan si no hay BD
uv run ruff check . && uv run ruff format --check .
```

- Fixtures en `tests/conftest.py`: `client` (httpx2 + lifespan), `db`, `v1_app`, `clean_users`.
- Tests con BD: `pytestmark = pytest.mark.db`. Se prueba contra MariaDB real, no SQLite.
- Override de dependencias: `v1_app.dependency_overrides[get_user_controller] = Fake`.
- `ENV_FILE=""` en tests: el `.env` local no se lee.
- `filterwarnings`: `DeprecationWarning`, `FastAPIDeprecationWarning`, `StarletteDeprecationWarning` y
  `UvicornDeprecationWarning` (y `RuntimeWarning`) son errores.

## Nombres

- Tablas: `database/init/00N_posts.sql` → tabla `posts`
- Models SQL: `app/models/post_model.py` → `PostModel`, `PostModelDep`
- Controllers: `app/controllers/post_controller.py` → `PostController`, `PostControllerDep`
- Services: `app/services/payments_service.py` → `PaymentsService`, `PaymentsServiceDep`
- Routes: `app/routes/v1/posts.py` → `router`
- Schemas: `app/schemas/post.py` → `PostCreate`, `PostUpdate`, `PostOut`
- Clases `PascalCase`, funciones/variables `snake_case`.

## Stack

FastAPI 0.142 · Starlette 1.7 · SQLAlchemy 2.1 (asyncio) + asyncmy · Pydantic 2.13 + pydantic-settings ·
limits · httpx · cryptography (Fernet) · sqids · uvicorn 0.54 · pytest-asyncio + httpx2 · Ruff · uv · Python ≥3.13 (3.14 por defecto).

## Comandos

```bash
cp .env.example .env
uv sync --all-groups
uv run fastapi dev                      # desarrollo con reload (reiniciar si cambia .env)
docker compose up -d --build            # db (vacía: aplicar database/*.sql con el gestor) → api → nginx
mariadb -h <host> -u <user> -p <db> < database/init/00N_x.sql   # cambio de esquema en BD existente
```

## Documentación

- `docs/features/`: detalle por feature (database, services, security, exceptions, logging, rate-limiting...).
- `docs/development/best-practices.md`, `docs/deployment.md`, `docs/docker-deployment.md`.
- Swagger en `/api/v1/docs`, ReDoc en `/api/v1/redoc` (deshabilitados por defecto en producción).

---

**Nota para agentes**: mantener la consistencia. Todo endpoint usa `ApiResponse[T]`, todo error
controlado usa `AppHttpException`, todo acceso a datos es `await db.*`, toda API externa es un
`ServiceClient`, nada bloqueante en `async def`.
Actualizar la documentación en el mismo cambio que el código.
