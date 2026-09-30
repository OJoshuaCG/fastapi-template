# Mejores Prácticas de Desarrollo

La plantilla es **100% async**: un solo hilo por worker atiende todas las requests. Cualquier llamada bloqueante dentro de un `async def` congela el worker completo (incluido `/health`). La mayoría de estas reglas existen para evitar eso.

---

## 1. Async: nunca bloquear el event loop

### Prohibido dentro de `async def`

| Bloqueante | Alternativa async |
|---|---|
| `requests`, `urllib`, `httpx.Client` | Un service que hereda de `ServiceClient` (`app/services/`) |
| `time.sleep()` | `await asyncio.sleep()` |
| Drivers síncronos (`pymysql`, `mysqlclient`, `psycopg2`) | `Database` (SQLAlchemy async + `asyncmy`) |
| `open()`, `Path.read_bytes()`, `shutil` | `anyio.Path`, `anyio.open_file` |
| CPU pesado (hash, pandas, PIL, PDF) o SDKs síncronos | `await anyio.to_thread.run_sync(func, ...)` |

```python
# ❌ Bloquea el worker entero mientras espera
@router.get("/rates")
async def rates():
    return requests.get("https://api.externa.com/rates").json()

# ✅ I/O async a través de un service (app/services/rates_service.py)
class RatesService(ServiceClient):
    name = "rates"
    base_url = "https://api.rates.example"

    async def current(self) -> dict:
        return await self.get_json("/rates")

@router.get("/rates", response_model=ApiResponse[dict])
async def rates(rates: RatesServiceDep):   # en un proyecto real: a través del controller
    return success(data=await rates.current())
```

Ruff tiene activas las reglas `ASYNC` (detecta `time.sleep`, `open`, `requests`... dentro de `async def`) y corre en pre-commit.

### Trabajo de CPU en un thread

La función síncrona se ejecuta con `anyio.to_thread.run_sync` y el endpoint solo la espera:

```python
from anyio import CapacityLimiter, to_thread

_limiter = CapacityLimiter(4)            # máx. 4 simultáneos si cada uno usa mucha memoria

async def build_report(data: list[dict]) -> bytes:
    return await to_thread.run_sync(_render_pdf_sync, data, limiter=_limiter)
```

Con trabajo de CPU que usa mucha memoria, acotar la concurrencia con un `CapacityLimiter` propio.

### Cliente HTTP: un pool por servicio externo

Crear un `httpx.AsyncClient` por request agota file descriptors y paga un handshake TLS en cada llamada.
Cada integración es un service que hereda de `ServiceClient`: su pool se crea en el primer uso, se reutiliza
y se cierra en el lifespan (`close_all()`). Pools separados: un proveedor lento no agota las conexiones de
otro. Ver [services](../features/services.md).

### `asyncio.create_task` necesita una referencia

El event loop guarda solo referencias débiles a las tareas: una tarea sin referencia puede ser recolectada a mitad de ejecución (Ruff `RUF006`).

```python
# ❌
asyncio.create_task(send_email(user))

# ✅
_background: set[asyncio.Task] = set()

task = asyncio.create_task(send_email(user))
_background.add(task)
task.add_done_callback(_background.discard)
```

Para trabajo que debe sobrevivir a la request o reintentarse, usar una cola (no tareas sueltas).

### Timeouts en todo I/O externo

```python
async with asyncio.timeout(5):
    await servicio_lento()
```

La BD ya tiene `DB_POOL_TIMEOUT`, `DB_CONNECT_TIMEOUT` y `DB_STATEMENT_TIMEOUT`; el cliente HTTP, `HTTP_CLIENT_TIMEOUT`.

### Detectar bloqueos del event loop

**Prevención (ya activa):** Ruff con las reglas `ASYNC` detecta llamadas bloqueantes dentro de `async def` (`time.sleep`, `open`, `requests`...), y pytest trata `RuntimeWarning` como error, así que una corrutina sin `await` hace fallar el test.

**En desarrollo:** el modo debug de asyncio registra cada callback que tarda más que `loop.slow_callback_duration` (default 100 ms), con la tarea que lo causó:

```bash
PYTHONASYNCIODEBUG=1 uv run fastapi dev
# WARNING asyncio: Executing <Task ... coro=<get_user() ...>> took 0.312 seconds
```

Solo para desarrollo: el modo debug agrega overhead.

**En producción:** `py-spy dump --pid <pid>` muestra el stack de cada thread en ese instante, sin tocar el código ni reiniciar (desde el host o dentro del contenedor, con permisos de `ptrace`). Si el worker está congelado, el stack señala al culpable. Si se necesita monitoreo continuo, usar una librería como [aiodebug](https://pypi.org/project/aiodebug/).

El template no incluye un monitor de lag del event loop a propósito: es poco común en plantillas y un monitor casero solo detecta *que* el loop se retrasó, no puede identificar de forma confiable *qué* lo bloqueó.

---

## 2. Base de Datos

### Parámetros siempre enlazados

```python
# ✅
await self.db.fetch_one("SELECT ... FROM users WHERE id = :id", {"id": user_id})

# ❌ SQL injection
await self.db.fetch_one(f"SELECT ... FROM users WHERE id = {user_id}")
```

### Nombres de columna dinámicos: solo desde whitelist

Los valores van como parámetros, pero los identificadores (columnas, ORDER BY) no se pueden parametrizar. Validarlos contra un conjunto fijo, como `UserModel.update`:

```python
_UPDATABLE_COLUMNS = frozenset({"email", "full_name", "notes", "is_active", "is_superuser", "encrypted_password"})

async def update(self, user_id: int, data: dict[str, Any]) -> int:
    unknown = set(data) - _UPDATABLE_COLUMNS
    if unknown:
        raise AppHttpException("Campos no permitidos", 422, {"fields": sorted(unknown)}, code="invalid_fields")
    set_clause = ", ".join(f"{col} = :{col}" for col in data)  # col ∈ whitelist
    result = await self.db.execute(f"UPDATE users SET {set_clause} WHERE id = :id", {**data, "id": user_id})
    return result.rowcount
```

### No compartir una conexión en `asyncio.gather`

Una conexión ejecuta una sentencia a la vez. Sin `conn=`, cada helper toma su propia conexión del pool, así que `gather` es seguro; con una transacción compartida, las sentencias van en secuencia.

```python
# ✅ Conexiones independientes (cada helper toma y devuelve la suya)
items, total = await asyncio.gather(model.find_all(limit=20, offset=0), model.count())

# ❌ La misma conexión en paralelo
async with db.transaction() as tx:
    await asyncio.gather(db.execute(a, conn=tx), db.execute(b, conn=tx))

# ✅ Dentro de una transacción: secuencial
async with db.transaction() as tx:
    await db.execute("UPDATE accounts SET ...", {...}, conn=tx)
    await db.execute("INSERT INTO movements ...", {...}, conn=tx)
```

Tener en cuenta que `gather` usa varias conexiones del pool por request.

### No mantener una conexión mientras se espera I/O externo

Una transacción abierta durante una llamada HTTP retiene la conexión (y los locks) todo ese tiempo; con carga, el pool se agota y las demás requests reciben 503.

```python
# ❌
async with db.transaction() as tx:
    order = await db.fetch_one("SELECT ... FOR UPDATE", {...}, conn=tx)
    await http.post("https://pagos.externo/charge", json=order)   # conexión retenida
    await db.execute("UPDATE orders SET paid = 1 ...", {...}, conn=tx)

# ✅ Leer → llamar afuera → escribir en una transacción corta
order = await model.find_by_id(order_id)
charge = await http.post("https://pagos.externo/charge", json=order)
await model.mark_paid(order_id, charge.json()["id"])
```

### Dejar que la BD decida la unicidad

No hacer `SELECT` para ver si existe antes de insertar (carrera TOCTOU). El índice `UNIQUE` decide y `Database` traduce el duplicado a 409 (`reason="duplicate"`), como en `UserController.create_user`.

### Sin columnas sensibles en las respuestas

Las consultas que terminan en una respuesta seleccionan columnas explícitas (ver `_PUBLIC_COLUMNS` en `UserModel`), nunca `encrypted_password`.

---

## 3. Estructura MVC e inyección

```python
# app/models/post_model.py
class PostModel:
    def __init__(self, db: Database):
        self.db = db

    async def find_by_id(self, post_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT id, title FROM posts WHERE id = :id", {"id": post_id})

def get_post_model(db: DatabaseDep) -> PostModel:
    return PostModel(db)

PostModelDep = Annotated[PostModel, Depends(get_post_model)]
```

```python
# app/controllers/post_controller.py
class PostController:
    def __init__(self, posts: PostModel):
        self.posts = posts

    async def get_post(self, post_id: int) -> dict:
        post = await self.posts.find_by_id(post_id)
        if not post:
            raise AppHttpException("Post no encontrado", 404, {"post_id": post_id}, code="post_not_found")
        return post

def get_post_controller(posts: PostModelDep) -> PostController:
    return PostController(posts)

PostControllerDep = Annotated[PostController, Depends(get_post_controller)]
```

```python
# app/routes/v1/posts.py
@router.get("/{post_id}", response_model=ApiResponse[PostOut])
async def get_post(post_id: int, posts: PostControllerDep):
    return success(data=await posts.get_post(post_id))
```

Registrar el router en `build_v1_router()` (`app/routes/v1/routes.py`). Sin lógica de negocio en las routes ni SQL en los controllers.

---

## 4. Respuestas y Errores

### Siempre `ApiResponse[T]`

```python
# ✅
@router.get("/{user_id}", response_model=ApiResponse[UserOut])
async def get_user(user_id: int, users: UserControllerDep):
    return success(data=await users.get_user(user_id))

# ❌ Rompe el formato estándar
@router.get("/{user_id}")
async def get_user(user_id: int):
    return {"id": 1}
```

### Siempre `AppHttpException`

```python
# ✅
raise AppHttpException("El email ya está en uso", 409, code="user_conflict")

# ❌
raise HTTPException(status_code=409, detail="conflict")
```

- `message`: texto seguro para el usuario final. Nunca `str(e)`.
- `code` / `reason`: identificadores estables para el frontend.
- `context`: datos de depuración (solo logs y development). Nunca el body completo (PII).
- Encadenar la causa: `raise AppHttpException(...) from e`.

### Capturar excepciones específicas

```python
# ✅
try:
    user_id = await self.users.create(data)
except AppHttpException as e:
    if e.reason == "duplicate":
        raise AppHttpException("El username o email ya está en uso", 409, code="user_conflict") from e
    raise

# ❌ Oculta el error real y devuelve un 500 genérico sin traza útil
try:
    ...
except Exception:
    pass
```

Los errores no controlados los registra `generic_exception_handler` una sola vez con traceback; no hace falta loguearlos a mano.

---

## 5. Validación

Schemas en `app/schemas/` con `extra="forbid"` para rechazar campos desconocidos:

```python
class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
```

En updates parciales usar `payload.model_dump(exclude_unset=True)`.

Estilo FastAPI/Pydantic moderno: `Field(min_length=...)` sin `...`; parámetros con `Annotated` en vez de defaults (`is_active: Annotated[bool | None, Query()] = None`, `file: Annotated[UploadFile, File()]`, `PaginationDep`, `UserControllerDep`); `status_code=status.HTTP_201_CREATED` en vez de `201`.

---

## 6. Rate Limiting

```python
from app.core.environment import settings
from app.core.rate_limit import rate_limit

@router.post("/login", dependencies=[rate_limit(settings.RATE_LIMIT_LOGIN)])  # leído al importar
async def login(...): ...
```

El límite global por IP lo aplica nginx (`limit_req`); en la app solo se limitan rutas concretas. Con más de un worker o réplica, usar Redis (`RATE_LIMIT_REDIS_ENABLED=True`, `uv sync --extra redis`): en memoria cada worker cuenta por separado.

El rate limit de la app es una dependencia y FastAPI la resuelve **después** de leer el body: no frena bodies grandes. El límite duro es `limit_req` de nginx (+ `RequestSizeMiddleware`).

---

## 7. Logging

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Pedido %s creado", order_id)           # el request_id se agrega solo
logger.warning("Proveedor lento: %.1fs", elapsed)
```

- No agregar el Request ID a mano: `logging_config` lo inyecta en cada línea.
- Usar `%s` (lazy) en lugar de f-strings en logs.
- Nunca loguear contraseñas, tokens ni bodies completos. `Authorization`, `Cookie` y cualquier header con nombre sensible (`is_sensitive_key`) se enmascaran solos en el LoggerMiddleware.
- `LOG_FORMAT=json` para agregadores (Loki, ELK, Datadog).

---

## 8. Seguridad

- Secretos solo por variables de entorno (`Settings` con `SecretStr`); `detect-secrets` corre en pre-commit.
- Contraseñas cifradas de forma reversible (`encrypt_password()` / `verify_password()` / `reveal_password()` de `app/utils/passwords.py`) con `ENCRYPTION_KEYS`; la llave se guarda y respalda fuera de la BD. Ver [security](../features/security.md).
- Un secreto por propósito: `SECRET_KEY`, `ENCRYPTION_KEYS`, `ENCODING_ALPHABET`, `DB_PASS` (en producción deben ser distintos).
- IDs públicos con `EncodedId`/`EncodedIdOut` (ofuscación, no autorización).
- En producción la app no arranca con `SECRET_KEY` < 32 caracteres, `DB_PASS` débil, `CORS_ORIGINS=*` o `ENCODING_ALPHABET` por defecto; en staging y producción, tampoco sin `ENCRYPTION_KEYS` o con `DOCS_PASSWORD` débil (docs protegidos). `SECRET_KEY` está reservado para la auth del proyecto.
- Uploads: `save_upload()` valida tipo y tamaño mientras copia; el MIME lo declara el cliente, validar el contenido si es crítico. Eliminar siempre el temporal en `finally`.

---

## 9. Testing

```bash
docker compose -f docker-compose.test.yml up -d --wait
uv run pytest
```

- Tests contra MariaDB real (no SQLite: SQL directo, SP, `SIGNAL` y collations son específicos de MariaDB/MySQL).
- Marcar con `pytestmark = pytest.mark.db` los tests que usan BD (se omiten solos si no hay BD).
- `asyncio_mode = "auto"`: los tests `async def` no necesitan decorador.
- Un `RuntimeWarning` (corrutina sin `await`) hace fallar el test, igual que cualquier `DeprecationWarning`, `FastAPIDeprecationWarning`, `StarletteDeprecationWarning` o `UvicornDeprecationWarning` (`filterwarnings` en `pyproject.toml`).
- `ENV_FILE=""` en `tests/conftest.py`: el `.env` local no afecta a los tests.
- Reemplazar dependencias sobre la sub-app: `v1_app.dependency_overrides[get_user_controller] = ...` (fixture `v1_app`).

```python
pytestmark = pytest.mark.db

async def test_get_user_404(client: httpx2.AsyncClient) -> None:
    response = await client.get("/api/v1/users/999999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "user_not_found"
```

---

## 10. Git y calidad

```bash
uv run --with pre-commit pre-commit install
uv run ruff check . && uv run ruff format --check .
```

Commits semánticos: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

---

## Recursos

- [FastAPI: async y concurrencia](https://fastapi.tiangolo.com/async/)
- [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html)
- [AnyIO: threads](https://anyio.readthedocs.io/en/stable/threads.html)
- [Ruff: reglas ASYNC](https://docs.astral.sh/ruff/rules/#flake8-async-async)
