"""Capa de datos contra MariaDB real."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Database, build_engine_kwargs, build_url, install_session_setup
from app.core.environment import settings
from app.exceptions import AppHttpException

pytestmark = pytest.mark.db


async def test_fetch_helpers_return_plain_dicts(db: Database, clean_users) -> None:
    result = await db.execute(
        "INSERT INTO users (username, email, encrypted_password) VALUES (:u, :e, 'x')",
        {"u": "ana", "e": "ana@example.com"},
    )
    assert result.rowcount == 1 and result.lastrowid

    row = await db.fetch_one(
        "SELECT id, username FROM users WHERE id = :id", {"id": result.lastrowid}
    )
    assert type(row) is dict and row["username"] == "ana"
    assert await db.fetch_one("SELECT id FROM users WHERE id = -1") is None
    assert await db.fetch_all("SELECT id FROM users WHERE id = -1") == []
    assert await db.fetch_value("SELECT COUNT(*) FROM users") == 1


async def test_transaction_rolls_back_on_error(db: Database, clean_users) -> None:
    with pytest.raises(RuntimeError):
        async with db.transaction() as tx:
            await db.execute(
                "INSERT INTO users (username, email, encrypted_password) "
                "VALUES ('tx', 'tx@x.com', 'x')",
                conn=tx,
            )
            raise RuntimeError("falla a mitad de la transacción")
    assert await db.fetch_value("SELECT COUNT(*) FROM users") == 0


async def test_duplicate_key_is_409(db: Database, clean_users) -> None:
    sql = "INSERT INTO users (username, email, encrypted_password) VALUES ('dup', 'dup@x.com', 'x')"
    await db.execute(sql)
    with pytest.raises(AppHttpException) as exc:
        await db.execute(sql)
    assert exc.value.status_code == 409
    assert exc.value.reason == "duplicate"


async def test_stored_procedure_from_database_folder(db: Database, clean_users) -> None:
    """sp_user_stats viene de database/procedures/ (aplicado por el fixture de esquema)."""
    await db.execute(
        "INSERT INTO users (username, email, encrypted_password, is_active) "
        "VALUES ('a', 'a@x.com', 'x', 1), ('b', 'b@x.com', 'x', 0)"
    )
    totals, latest = await db.call_procedure("sp_user_stats", [0])
    assert totals == [{"total": 2, "active": 1}]
    assert [u["username"] for u in latest] == ["b", "a"]

    # La conexión volvió limpia al pool: la siguiente consulta funciona
    assert await db.fetch_value("SELECT 1") == 1

    with pytest.raises(AppHttpException) as exc:
        await db.call_procedure("sp_user_stats", [7])
    assert exc.value.status_code == 409
    assert exc.value.code == "business_rule"
    assert exc.value.message == "El filtro only_active debe ser 0 o 1"
    assert exc.value.context["params"] == {"count": 1}  # nunca los valores

    with pytest.raises(ValueError):
        await db.call_procedure("sp; DROP TABLE users")


async def test_statement_timeout_is_504_and_connection_is_reusable(db: Database) -> None:
    # DB_STATEMENT_TIMEOUT=2 en conftest
    with pytest.raises(AppHttpException) as exc:
        await db.fetch_value("SELECT SLEEP(5)")
    assert exc.value.status_code == 504
    assert await db.fetch_value("SELECT 1") == 1


async def test_pool_exhaustion_fails_fast_without_blocking_the_loop() -> None:
    """Con el pool lleno: 503 rápido (pool_timeout) y el event loop sigue atendiendo."""
    tiny_pool = {"pool_size": 1, "max_overflow": 0, "pool_timeout": 0.5}
    kwargs = build_engine_kwargs(settings) | tiny_pool
    engine = create_async_engine(build_url(settings), **kwargs)
    install_session_setup(engine, settings)
    db = Database(engine)

    loop = asyncio.get_running_loop()
    gaps: list[float] = []
    stop = asyncio.Event()

    async def heartbeat() -> None:
        last = loop.time()
        while not stop.is_set():
            await asyncio.sleep(0.01)
            now = loop.time()
            gaps.append(now - last)
            last = now

    beat = asyncio.create_task(heartbeat())
    try:
        async with engine.connect() as held:  # ocupa la única conexión
            await held.exec_driver_sql("SELECT 1")
            started = loop.time()
            with pytest.raises(AppHttpException) as exc:
                await db.fetch_value("SELECT 1")
            waited = loop.time() - started
    finally:
        stop.set()
        await beat
        await engine.dispose()

    assert exc.value.status_code == 503
    assert exc.value.reason == "pool_exhausted"
    assert waited < 1.5
    assert max(gaps) < 0.1, "el event loop se bloqueó mientras se esperaba el pool"


async def test_queries_run_concurrently(db: Database) -> None:
    """10 × SLEEP(0.5) concurrentes terminan en ~0.5s: el driver no bloquea el loop."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    await asyncio.gather(*(db.fetch_value("SELECT SLEEP(0.5)") for _ in range(10)))
    assert loop.time() - started < 1.5


async def test_cancelled_query_does_not_poison_the_pool(db: Database) -> None:
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.2):
            await db.fetch_value("SELECT SLEEP(1)")
    # Las siguientes consultas funcionan (la conexión cancelada no volvió sucia al pool)
    for _ in range(3):
        assert await db.fetch_value("SELECT 1") == 1
