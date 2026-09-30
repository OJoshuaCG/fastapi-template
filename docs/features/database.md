# Base de Datos

Acceso async a **MariaDB / MySQL** con SQLAlchemy 2.1 (`sqlalchemy[asyncio]`) y el driver `asyncmy`. Todo el código está en `app/core/database.py`.

- **SQL directo** en runtime: `Database` (`fetch_one`, `fetch_all`, `fetch_value`, `execute`, `transaction`, `call_procedure`, `ping`).
- **Esquema en SQL plano** (`database/`): tablas y stored procedures en scripts `.sql`. No se usa ORM ni Alembic
  por defecto; para usar Alembic hay que agregar la librería (`uv add alembic`), ver `database/README.md`.

Solo se soporta MariaDB/MySQL: la traducción de errores, los timeouts de sentencia, `SIGNAL` y los stored procedures dependen de ese motor. Los tests corren contra MariaDB real (`docker-compose.test.yml`), no SQLite.

## Configuración

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=app
DB_PASS=
DB_NAME=app
DB_COLLATION=utf8mb4_unicode_ci

# Pool (por worker)
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=3        # segundos esperando conexión libre → 503
DB_POOL_RECYCLE=180      # debe ser < wait_timeout del servidor
DB_CONNECT_TIMEOUT=5
DB_STATEMENT_TIMEOUT=30  # segundos por sentencia en el servidor (0 = sin límite)
```

La URL se construye con `URL.create("mysql+asyncmy", ...)`, que escapa las credenciales (un `@` en la contraseña no rompe nada). Charset siempre `utf8mb4`.

Al abrir cada conexión nueva se ejecuta:

- `SET NAMES utf8mb4 COLLATE <DB_COLLATION>`
- Timeout de sentencia: `SET SESSION max_statement_time = N` (MariaDB, segundos) o, si falla, `SET SESSION MAX_EXECUTION_TIME = N*1000` (MySQL, milisegundos).

> MariaDB no aplica `max_statement_time` dentro de stored procedures; MySQL solo lo aplica a `SELECT`.

### Collation (`DB_COLLATION`)

`DB_COLLATION` es la collation de la **sesión** (`SET NAMES` en cada conexión) y debe coincidir con la de la base y sus tablas. Si difieren, MariaDB puede fallar con `Illegal mix of collations`: variables o parámetros en SPs, `CONCAT` con literales y tablas temporales toman la de la sesión y se comparan contra columnas con otra.

- `docker-compose.yml` (y `docker-compose.test.yml`) arrancan MariaDB con `--character-set-server=utf8mb4 --collation-server=${DB_COLLATION:-utf8mb4_unicode_ci}`, así la base que crea el contenedor coincide.
- En otro servidor, crear la base con la misma: `CREATE DATABASE app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`

## Engine y ciclo de vida

- **Un engine (y un pool) por proceso/worker.** `get_engine()` lo crea perezosamente en el primer uso, es decir, después del fork de cada worker de uvicorn.
- `dispose_engine()` cierra el pool. Se llama en el shutdown del **lifespan de la app raíz** (`main.py`). Las sub-apps montadas no ejecutan lifespan.
- En el arranque, el lifespan hace `ping()` como calentamiento. Si falla, solo se registra un warning y la app arranca igual; `/ready` reporta el estado real.
- Nunca crear engines por request ni por modelo.

En scripts o jobs fuera de la app:

```python
import asyncio

from app.core.database import dispose_engine, get_database


async def main() -> None:
    db = get_database()
    try:
        total = await db.fetch_value("SELECT COUNT(*) FROM users")
        print(total)
    finally:
        await dispose_engine()


asyncio.run(main())
```

### Tamaño del pool

Cada worker tiene su propio pool. La regla es:

```
WORKERS × (DB_POOL_SIZE + DB_MAX_OVERFLOW) × réplicas  <  max_connections del servidor
```

Deja margen para scripts de esquema, consolas y otros servicios. Con los defaults (1 worker, 10 + 10) se usan hasta 20 conexiones.

- `pool_pre_ping=True`: valida la conexión antes de entregarla.
- `DB_POOL_RECYCLE` **menor que `wait_timeout`** del servidor. Si no, el pool entrega conexiones que el servidor ya cerró y aparece "MySQL server has gone away".
- `DB_POOL_TIMEOUT` es bajo a propósito (3s, contra 30s por defecto en SQLAlchemy). Con el pool lleno, esperar no ayuda: responde 503 rápido en vez de congelar el worker.

## API de `Database`

`Database` es una fachada sin estado sobre el engine y es barata de instanciar. En endpoints se inyecta con `DatabaseDep`:

```python
from app.core.database import Database, DatabaseDep
```

| Método | Retorna | Conexión |
|---|---|---|
| `fetch_one(sql, params=None, *, conn=None)` | `dict \| None` (primera fila) | `connect()`, sin commit |
| `fetch_all(sql, params=None, *, conn=None)` | `list[dict]` | `connect()`, sin commit |
| `fetch_value(sql, params=None, *, conn=None)` | primera columna de la primera fila | `connect()`, sin commit |
| `execute(sql, params=None, *, conn=None)` | `ExecResult(rowcount, lastrowid)` | `begin()`: commit al salir, rollback si falla |
| `transaction()` | context manager con un `AsyncConnection` | `begin()` |
| `call_procedure(name, params=None)` | `list[list[dict]]` (todos los result sets) | `begin()`, conexión propia |
| `ping()` | `None` (lanza 503 si no responde) | `SELECT 1` |

Cada helper abre una conexión, ejecuta, convierte el resultado a dicts y **devuelve la conexión al pool antes de retornar**. Nunca se devuelve un `Result` vivo.

Los parámetros siempre van nombrados (`:id`) y se pasan en un dict:

```python
# ✅ Parámetros
await db.fetch_one("SELECT * FROM users WHERE id = :id", {"id": user_id})

# ❌ Nunca interpolar valores: SQL injection
await db.fetch_one(f"SELECT * FROM users WHERE id = {user_id}")
```

Si tienes que interpolar nombres de columna (por ejemplo en un `UPDATE` dinámico), valídalos contra una whitelist, como hace `UserModel.update`.

## Patrón Model → Controller → Route

Los models reciben `Database` por constructor y exponen métodos async que retornan dicts. Se inyectan con `Depends`, así que en tests se pueden reemplazar.

```python
# app/models/post_model.py
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.database import Database, DatabaseDep


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

    async def create(self, data: dict[str, Any], *, conn: AsyncConnection | None = None) -> int:
        result = await self.db.execute(
            "INSERT INTO posts (title, content) VALUES (:title, :content)",
            {"title": data["title"], "content": data.get("content")},
            conn=conn,
        )
        return int(result.lastrowid or 0)


def get_post_model(db: DatabaseDep) -> PostModel:
    return PostModel(db)


PostModelDep = Annotated[PostModel, Depends(get_post_model)]
```

El controller recibe el model de la misma forma (ver `app/controllers/user_controller.py`) y la route recibe el controller con `UserControllerDep`/`PostControllerDep`. El ejemplo completo está en `app/models/user_model.py`, `app/controllers/user_controller.py` y `app/routes/v1/users.py`.

## Transacciones

Si varias sentencias tienen que ser atómicas, usa `transaction()` y pasa `conn=tx` a **cada** llamada. Dentro de una transacción los helpers no hacen commit ni rollback: el bloque `async with` hace commit al salir y rollback si ocurre cualquier excepción.

```python
async with db.transaction() as tx:
    await db.execute(
        "UPDATE accounts SET balance = balance - :amount WHERE id = :id",
        {"amount": amount, "id": from_id},
        conn=tx,
    )
    await db.execute(
        "INSERT INTO movements (account_id, amount) VALUES (:id, :amount)",
        {"id": from_id, "amount": -amount},
        conn=tx,
    )
```

Si un model necesita participar, sus métodos aceptan `conn` y lo propagan (como `UserModel.create/update/find_by_id`):

```python
async with self.db.transaction() as tx:
    post_id = await self.posts.create(data, conn=tx)
    await self.tags.attach(post_id, tags, conn=tx)
```

Una llamada **sin** `conn=tx` dentro del bloque toma otra conexión del pool y queda fuera de la transacción: no ve los cambios pendientes y no se revierte.

> `call_procedure()` no acepta `conn`: siempre usa su propia conexión y hace commit. No puede formar parte de una `transaction()`.

## Stored procedures

Ejemplo incluido: `database/procedures/sp_user_stats.sql` (`DELIMITER`, 2 result sets y `SIGNAL`).

```python
result_sets = await db.call_procedure("sp_user_stats", [1])  # 1 = solo activos, 0 = todos
# [[{"total": 3, "active": 3}], [{"id": 7, "username": "ana"}, ...]]  → siempre una lista de result sets
totals, latest = result_sets[0][0], result_sets[1]

await db.call_procedure("sp_user_stats", [5])  # SIGNAL 45000 → 409 "El filtro only_active debe ser 0 o 1"
```

- Se leen **todos** los result sets, incluido el de estado del `CALL`, y el cursor se cierra siempre. Si quedan resultados sin leer, la conexión vuelve "sucia" al pool.
- El nombre se valida con una regex (`nombre` o `schema.nombre`), porque `callproc` lo interpola sin escapar. Un nombre inválido lanza `ValueError`.
- `SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '...'` dentro del SP responde **409** con `code="business_rule"` y **el mensaje del SP llega al cliente**. Escribe esos mensajes pensando en el usuario final.
- Los parámetros son posicionales (no se pueden enmascarar por nombre): si el SP falla, el `context` del error solo lleva `{"count": N}`, **nunca los valores**.

## Traducción de errores

Los errores de SQLAlchemy y del driver se convierten en `AppHttpException` (`translate_db_error`). El `context` (tipo de error, código MySQL, mensaje, SQL y params sanitizados; en `call_procedure` solo la cantidad de params) solo aparece en la respuesta en development y siempre en el log de los 5xx.

| Situación | Status | `code` | `reason` | Mensaje |
|---|---|---|---|---|
| Pool agotado (`DB_POOL_TIMEOUT`) | 503 + `Retry-After: 1` | `db_unavailable` | `pool_exhausted` | Servicio saturado, intenta de nuevo en unos segundos |
| `SIGNAL SQLSTATE '45000'` (1644) | 409 | `business_rule` | — | El mensaje del SP/trigger |
| Clave duplicada (1062) | 409 | `conflict` | `duplicate` | El registro ya existe |
| FK (1451/1452) u otra `IntegrityError` | 409 | `conflict` | `integrity` | La operación viola la integridad de los datos |
| Timeout de sentencia (1969 MariaDB / 3024 MySQL) | 504 | `db_timeout` | `statement_timeout` | La consulta tardó demasiado |
| Conexión perdida (2002, 2003, 2006, 2013, 4031) | 503 + `Retry-After: 1` | `db_unavailable` | `connection_lost` | Base de datos no disponible |
| Cualquier otro error de BD | 500 | `db_error` | — | Ocurrió un error inesperado en el servidor |

Para dar un mensaje de negocio, captura la excepción traducida en el controller y usa `reason`. **No hagas un SELECT previo para ver si existe**, porque tiene carrera (TOCTOU). Deja que decida el índice `UNIQUE`:

```python
try:
    user_id = await self.users.create(data)
except AppHttpException as e:
    if e.reason == "duplicate":
        raise AppHttpException("El username o email ya está en uso", 409, code="user_conflict") from e
    raise
```

## Reglas de uso de conexiones

1. **Unidad de trabajo corta.** Una conexión se toma, se usa y se devuelve. Los helpers ya lo hacen. No guardes `AsyncConnection` en atributos ni en variables globales.
2. **Nunca mantengas una conexión o transacción abierta mientras esperas I/O externa** (HTTP, colas, correo, archivos grandes). Mientras esperas, la conexión sigue ocupada en el pool y los locks siguen tomados. Primero haz la llamada externa y después abre la transacción:

   ```python
   # ❌ La conexión queda retenida mientras responde el servicio externo
   async with db.transaction() as tx:
       await db.execute("UPDATE orders SET status = 'paying' WHERE id = :id", {"id": oid}, conn=tx)
       resp = await http.post("https://pagos.example/charge", json=payload)

   # ✅ I/O externa fuera; transacción corta después
   resp = await http.post("https://pagos.example/charge", json=payload)
   async with db.transaction() as tx:
       await db.execute(
           "UPDATE orders SET status = :s WHERE id = :id",
           {"s": "paid" if resp.is_success else "failed", "id": oid},
           conn=tx,
       )
   ```

3. **Nunca uses `asyncio.gather` sobre la misma conexión o transacción.** Una conexión solo ejecuta una sentencia a la vez. `gather` sobre helpers **sin** `conn` sí funciona (cada uno toma su propia conexión), pero consume N conexiones del pool por request. En el caso normal, consultas secuenciales (como `UserController.list_users`).
4. **Lecturas sin transacción, escrituras con commit.** `fetch_*` usan `connect()` y `execute` usa `begin()`. Para varias escrituras atómicas, `transaction()` + `conn=tx`.
5. **Cancelación segura.** Si el cliente se desconecta o un `asyncio.timeout` cancela una consulta, la conexión no vuelve contaminada al pool (hay un test que lo cubre).
6. **Nada bloqueante en `async def`.** Nada de drivers síncronos (`pymysql`, `requests`) ni `time.sleep`. Ver [Detectar bloqueos del event loop](../development/best-practices.md#detectar-bloqueos-del-event-loop).

### BackgroundTasks y tareas fuera de la request

Las `BackgroundTasks` corren **después** de enviar la respuesta. Tienen que abrir su propia unidad de trabajo:

```python
from fastapi import APIRouter, BackgroundTasks

from app.core.database import get_database
from app.utils.response import ApiResponse, empty

router = APIRouter(prefix="/users", tags=["Users"])


async def recalculate_stats(user_id: int) -> None:
    db = get_database()  # fachada sin estado: toma sus propias conexiones
    async with db.transaction() as tx:
        ...


@router.post("/{user_id}/recalculate", response_model=ApiResponse[None])
async def recalculate(user_id: int, background: BackgroundTasks):
    background.add_task(recalculate_stats, user_id)
    return empty("Recalculo en proceso")
```

- Pasa **ids y datos**, nunca un `conn`/`tx` ni un `Result` de la request: cuando corre la tarea, esa conexión ya volvió al pool.
- Una tarea en background ocupa conexiones del mismo pool y corre en el mismo worker. Para trabajos largos o que deban sobrevivir a un reinicio, usa una cola.

## Health checks

- `GET /health` (liveness) no toca la BD, así que una caída de la BD no provoca reinicios del contenedor.
- `GET /ready` (readiness) hace `db.ping()` con un timeout de 2s. Responde `{"status": "ok", "checks": {"database": "up"}}` o **503** `{"status": "unavailable", "checks": {"database": "down"}}`.

## Esquema (`database/`)

El esquema se mantiene en SQL plano; la app no declara tablas ni modifica el esquema al arrancar:

- `database/init/NNN_descripcion.sql`: tablas y datos base, aplicados en orden (ej. `001_users.sql`). Usar `CREATE TABLE IF NOT EXISTS` y `utf8mb4` / `utf8mb4_unicode_ci`; `updated_at` con `ON UPDATE CURRENT_TIMESTAMP` del servidor.
- `database/procedures/sp_nombre.sql`: stored procedures (`DROP PROCEDURE IF EXISTS` + `DELIMITER` + `CREATE PROCEDURE`, ver `sp_user_stats.sql`).

Cómo se aplican:

- **docker-compose / desarrollo**: la base arranca **vacía**. Cada desarrollador aplica `database/init/*.sql` y luego `database/procedures/*.sql` con su gestor de BD (DBeaver, HeidiSQL, DataGrip...) o con `mariadb -h <host> -u $DB_USER -p $DB_NAME < archivo.sql` (los procedures usan `DELIMITER`: cliente `mariadb` o un gestor que lo soporte).
- **Tests**: la fixture `database_schema` de `tests/conftest.py` borra todas las tablas de la BD de test y aplica `database/init/*.sql` + `database/procedures/*.sql` (`sql_statements()` respeta `DELIMITER`).
- **BD existente**: cada cambio es un script nuevo numerado (nunca editar uno ya aplicado), aplicado a mano o por el DBA:

```bash
mariadb -h <host> -u <user> -p <db> < database/init/002_add_posts.sql
```

Más detalle en [database/README.md](../../database/README.md).

## Tests

```bash
docker compose -f docker-compose.test.yml up -d --wait
uv run pytest
```

Los tests marcados con `@pytest.mark.db` se saltan si la BD de test no está disponible. Para aislar la capa HTTP de la BD, reemplaza dependencias con `dependency_overrides` (ver [API Versionada](api-versioning.md#tests-y-dependency_overrides)).

---

Ver también: [Manejo de Excepciones](exceptions.md) · [Paginación](pagination.md)
