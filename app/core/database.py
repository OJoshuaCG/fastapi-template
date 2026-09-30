"""
Acceso a base de datos async (MariaDB / MySQL vía asyncmy).

Reglas que evitan los problemas clásicos (event loop bloqueado, conexiones "sleep",
pool agotado, "MySQL server has gone away"):

1. Un solo engine (y pool) por proceso/worker. Se crea perezosamente en el primer uso y se
   libera en el lifespan de la app raíz con `dispose_engine()`. Nunca crear engines por request.
2. Unidad de trabajo corta: cada helper abre una conexión, ejecuta, materializa el resultado
   a dicts y la devuelve al pool antes de retornar. Nunca se devuelve un Result vivo.
3. Lecturas con `engine.connect()` (sin commit), escrituras con `engine.begin()`
   (commit al salir, rollback si hay excepción).
4. Varias sentencias atómicas: `async with db.transaction() as tx` y pasar `conn=tx`.
5. No mantener una conexión/transacción abierta mientras se espera I/O externa (HTTP, colas).
6. Stored procedures: se drenan TODOS los result sets y se cierra el cursor siempre.
7. Pool: pre_ping + recycle < wait_timeout + pool_timeout bajo (fallar rápido con 503).

Uso:
    from app.core.database import DatabaseDep

    class PostModel:
        def __init__(self, db: Database):
            self.db = db

        async def find_by_id(self, post_id: int) -> dict | None:
            return await self.db.fetch_one("SELECT * FROM posts WHERE id = :id", {"id": post_id})
"""

import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar

from fastapi import Depends
from sqlalchemy import URL, event, text
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core import environment as env
from app.core.environment import Settings
from app.exceptions.AppHttpException import AppHttpException
from app.utils.dict_utils import sanitize

logger = logging.getLogger(__name__)

T = TypeVar("T")
Params = Mapping[str, Any] | None

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None


def build_url(settings: Settings | None = None) -> URL:
    """URL de conexión. URL.create escapa credenciales (un '@' en la contraseña no rompe nada)."""
    s = settings or env.settings
    return URL.create(
        "mysql+asyncmy",
        username=s.DB_USER or None,
        password=s.DB_PASS.get_secret_value() or None,
        host=s.DB_HOST,
        port=s.DB_PORT,
        database=s.DB_NAME or None,
        query={"charset": "utf8mb4"},
    )


def build_engine_kwargs(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or env.settings
    return {
        "pool_size": s.DB_POOL_SIZE,
        "max_overflow": s.DB_MAX_OVERFLOW,
        "pool_timeout": s.DB_POOL_TIMEOUT,
        "pool_recycle": s.DB_POOL_RECYCLE,
        "pool_pre_ping": True,
        "connect_args": {"connect_timeout": s.DB_CONNECT_TIMEOUT},
    }


def install_session_setup(engine: AsyncEngine, settings: Settings | None = None) -> None:
    """Configura cada conexión nueva: collation y timeout de sentencia en el servidor."""
    s = settings or env.settings
    collation = s.DB_COLLATION
    if not re.fullmatch(r"[A-Za-z0-9_]+", collation):
        raise ValueError(f"DB_COLLATION inválido: {collation!r}")
    timeout = float(s.DB_STATEMENT_TIMEOUT)

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET NAMES utf8mb4 COLLATE {collation}")
            if timeout > 0:
                try:
                    # MariaDB (segundos). No aplica dentro de stored procedures.
                    cursor.execute(f"SET SESSION max_statement_time = {timeout}")
                except Exception:
                    # MySQL (milisegundos, solo SELECT)
                    cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout * 1000)}")
        finally:
            cursor.close()


def get_engine() -> AsyncEngine:
    """Engine del proceso. Se crea en el primer uso (después del fork de cada worker)."""
    global _engine
    if _engine is None:
        settings = env.settings
        _engine = create_async_engine(build_url(settings), **build_engine_kwargs(settings))
        install_session_setup(_engine, settings)
    return _engine


async def dispose_engine() -> None:
    """Cierra el pool. Llamar en el shutdown del lifespan raíz y al final de scripts/jobs."""
    global _engine
    if _engine is not None:
        engine, _engine = _engine, None
        await engine.dispose()


# ---------------------------------------------------------------------------
# Traducción de errores
# ---------------------------------------------------------------------------

_MYSQL_SIGNAL = 1644  # SIGNAL SQLSTATE '45000' desde un SP/trigger
_DUPLICATE_KEY = 1062
_FK_ERRORS = {1451, 1452}
_STATEMENT_TIMEOUT = {1969, 3024}  # MariaDB max_statement_time, MySQL MAX_EXECUTION_TIME
_CONNECTION_LOST = {2002, 2003, 2006, 2013, 4031}


def _db_error_code(error: BaseException) -> int | None:
    args = getattr(error, "args", ())
    if args and isinstance(args[0], int):
        return args[0]
    return None


def _db_error_message(error: BaseException) -> str:
    args = getattr(error, "args", ())
    if len(args) > 1 and isinstance(args[1], str):
        return args[1]
    return str(error)


def is_db_error(error: BaseException) -> bool:
    """Error de SQLAlchemy o del driver (asyncmy); no incluye errores de negocio."""
    if isinstance(error, sa_exc.SQLAlchemyError):
        return True
    return type(error).__module__.split(".")[0] == "asyncmy"


def translate_db_error(
    error: BaseException, *, sql: str | None = None, params: Any = None
) -> AppHttpException:
    """Convierte errores de SQLAlchemy / del driver en AppHttpException con el status correcto."""
    if isinstance(error, AppHttpException):
        return error

    # Errores del driver crudo (call_procedure) llegan sin el envoltorio de SQLAlchemy
    orig = getattr(error, "orig", None) or error
    code = _db_error_code(orig)
    context = {
        "error_type": type(orig).__name__,
        "db_code": code,
        "db_message": _db_error_message(orig),
        "sql": sql,
        "params": sanitize(dict(params) if isinstance(params, Mapping) else params),
    }

    if isinstance(error, sa_exc.TimeoutError):  # pool agotado (NO es el TimeoutError builtin)
        return AppHttpException(
            "Servicio saturado, intenta de nuevo en unos segundos",
            503,
            code="db_unavailable",
            reason="pool_exhausted",
            headers={"Retry-After": "1"},
            context=context,
        )
    if code == _MYSQL_SIGNAL:
        # El mensaje del SP llega al cliente: los SP deben escribir mensajes aptos para usuario
        return AppHttpException(_db_error_message(orig), 409, code="business_rule", context=context)
    if code == _DUPLICATE_KEY:
        return AppHttpException(
            "El registro ya existe", 409, code="conflict", reason="duplicate", context=context
        )
    if code in _FK_ERRORS or isinstance(error, sa_exc.IntegrityError):
        return AppHttpException(
            "La operación viola la integridad de los datos",
            409,
            code="conflict",
            reason="integrity",
            context=context,
        )
    if code in _STATEMENT_TIMEOUT:
        return AppHttpException(
            "La consulta tardó demasiado",
            504,
            code="db_timeout",
            reason="statement_timeout",
            context=context,
        )
    if code in _CONNECTION_LOST or getattr(error, "connection_invalidated", False):
        return AppHttpException(
            "Base de datos no disponible",
            503,
            code="db_unavailable",
            reason="connection_lost",
            headers={"Retry-After": "1"},
            context=context,
        )
    return AppHttpException(
        "Ocurrió un error inesperado en el servidor", 500, code="db_error", context=context
    )


# ---------------------------------------------------------------------------
# API de datos
# ---------------------------------------------------------------------------

_SP_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*)?")


@dataclass(frozen=True, slots=True)
class ExecResult:
    rowcount: int
    lastrowid: int | None


class Database:
    """
    Fachada sin estado sobre el engine async. Barata de instanciar.

    fetch_one/fetch_all/fetch_value/execute aceptan `conn=` para participar en una transacción
    abierta con `transaction()`; en ese caso NO hacen commit ni rollback (lo decide el dueño de
    la transacción). `call_procedure` siempre abre su propia transacción corta.
    """

    def __init__(self, engine: AsyncEngine | None = None):
        self._engine = engine

    @property
    def engine(self) -> AsyncEngine:
        return self._engine or get_engine()

    async def _run(
        self,
        op: Callable[[AsyncConnection], Awaitable[T]],
        *,
        write: bool,
        conn: AsyncConnection | None,
        sql: str,
        params: Any,
    ) -> T:
        try:
            if conn is not None:
                return await op(conn)
            ctx = self.engine.begin() if write else self.engine.connect()
            async with ctx as connection:
                return await op(connection)
        except Exception as e:
            if not is_db_error(e):
                raise
            raise translate_db_error(e, sql=sql, params=params) from e

    async def fetch_one(
        self, sql: str, params: Params = None, *, conn: AsyncConnection | None = None
    ) -> dict[str, Any] | None:
        """Primera fila como dict, o None."""

        async def op(c: AsyncConnection) -> dict[str, Any] | None:
            row = (await c.execute(text(sql), dict(params or {}))).mappings().first()
            return dict(row) if row is not None else None

        return await self._run(op, write=False, conn=conn, sql=sql, params=params)

    async def fetch_all(
        self, sql: str, params: Params = None, *, conn: AsyncConnection | None = None
    ) -> list[dict[str, Any]]:
        """Todas las filas como lista de dicts."""

        async def op(c: AsyncConnection) -> list[dict[str, Any]]:
            result = await c.execute(text(sql), dict(params or {}))
            return [dict(row) for row in result.mappings().all()]

        return await self._run(op, write=False, conn=conn, sql=sql, params=params)

    async def fetch_value(
        self, sql: str, params: Params = None, *, conn: AsyncConnection | None = None
    ) -> Any:
        """Primera columna de la primera fila (COUNT(*), EXISTS, etc.)."""

        async def op(c: AsyncConnection) -> Any:
            return (await c.execute(text(sql), dict(params or {}))).scalar()

        return await self._run(op, write=False, conn=conn, sql=sql, params=params)

    async def execute(
        self, sql: str, params: Params = None, *, conn: AsyncConnection | None = None
    ) -> ExecResult:
        """INSERT / UPDATE / DELETE. Hace commit (salvo dentro de `transaction()`)."""

        async def op(c: AsyncConnection) -> ExecResult:
            result = await c.execute(text(sql), dict(params or {}))
            lastrowid = getattr(result, "lastrowid", None) or None
            return ExecResult(rowcount=result.rowcount, lastrowid=lastrowid)

        return await self._run(op, write=True, conn=conn, sql=sql, params=params)

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncConnection]:
        """
        Varias sentencias atómicas. Commit al salir, rollback si hay excepción.

            async with db.transaction() as tx:
                await db.execute("UPDATE accounts SET ...", {...}, conn=tx)
                await db.execute("INSERT INTO movements ...", {...}, conn=tx)
        """
        try:
            async with self.engine.begin() as conn:
                yield conn
        except Exception as e:
            # Solo se traducen errores de BD; los del bloque del usuario se relanzan tal cual
            if not is_db_error(e):
                raise
            raise translate_db_error(e) from e

    async def call_procedure(
        self, name: str, params: Sequence[Any] | None = None
    ) -> list[list[dict[str, Any]]]:
        """
        Ejecuta un stored procedure (MariaDB/MySQL) y retorna TODOS sus result sets.

        Siempre retorna una lista de result sets (cada uno lista de dicts):
            [[{...}, {...}], [{...}]]

        SIGNAL SQLSTATE '45000' en el SP → 409 con el mensaje del SP.
        """
        if not _SP_NAME.fullmatch(name):  # callproc interpola el nombre sin escapar
            raise ValueError(f"Nombre de stored procedure inválido: {name!r}")
        args = tuple(params or ())

        async def op(c: AsyncConnection) -> list[list[dict[str, Any]]]:
            raw = await c.get_raw_connection()
            cursor = raw.driver_connection.cursor()  # type: ignore[union-attr]
            try:
                await cursor.callproc(name, args)
                result_sets: list[list[dict[str, Any]]] = []
                while True:
                    if cursor.description:
                        columns = [col[0] for col in cursor.description]
                        rows = await cursor.fetchall()
                        result_sets.append([dict(zip(columns, row, strict=True)) for row in rows])
                    # Drenar todos los sets (incluido el de estado del CALL): si quedan
                    # resultados sin leer la conexión vuelve "sucia" al pool
                    if not await cursor.nextset():
                        break
                return result_sets
            finally:
                await cursor.close()

        # Los parámetros posicionales no tienen nombre (no se pueden enmascarar por clave):
        # al contexto de error solo va la cantidad, nunca los valores
        return await self._run(
            op, write=True, conn=None, sql=f"CALL {name}", params={"count": len(args)}
        )

    async def ping(self) -> None:
        """SELECT 1. Lanza AppHttpException 503 si la base no responde."""
        await self.fetch_value("SELECT 1")


def get_database() -> Database:
    return Database()


DatabaseDep = Annotated[Database, Depends(get_database)]
