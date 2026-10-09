# Acceso a datos y SQL

Reglas del acceso a la base de datos (SQL directo, async, sin ORM). Léelo antes de escribir un model, una consulta o un stored procedure.

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

## Seguridad SQL

```python
# ✅ Siempre parámetros
await db.fetch_one("SELECT * FROM users WHERE id = :id", {"id": user_id})

# ❌ Nunca interpolar valores (SQL injection)
await db.fetch_one(f"SELECT * FROM users WHERE id = {user_id}")
```

Si hay que interpolar nombres de columna (UPDATE dinámico, ORDER BY), validarlos contra una whitelist
(ver `UserModel.update`). Para filtros y orden de listados usar `WhereBuilder` y `order_by()`
(`app/core/sql_filters.py`, ver `docs/features/pagination.md`).

