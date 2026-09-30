"""
Fixtures de tests.

Los tests con BD corren contra MariaDB real (no SQLite: el SQL directo, los SP, SIGNAL
y las collations son específicos de MariaDB/MySQL):

    docker compose -f docker-compose.test.yml up -d --wait
    uv run pytest

Variables TEST_DB_* permiten apuntar a otra instancia (CI).
"""

import os

# Entorno de test ANTES de importar la app (settings se valida al importar app.core.environment)
os.environ.update(
    {
        # No leer el .env del desarrollador: los tests solo dependen de estas variables
        "ENV_FILE": "",
        "APP_ENV": "test",
        "DB_HOST": os.getenv("TEST_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.getenv("TEST_DB_PORT", "3307"),
        "DB_USER": os.getenv("TEST_DB_USER", "app_test"),
        "DB_PASS": os.getenv("TEST_DB_PASS", "app_test_pass"),
        "DB_NAME": os.getenv("TEST_DB_NAME", "app_test"),
        "DB_STATEMENT_TIMEOUT": "2",
        "CORS_ORIGINS": "https://ok.example",
        "OTEL_ENABLED": "false",
        "RATE_LIMIT_LOGIN": "3/minute",
        "LOGGER_EXCEPTIONS_ENABLED": "true",
        # Llave fija SOLO de tests (nunca usarla fuera de aquí)
        "ENCRYPTION_KEYS": "wg4RA2dIKUHMj4_YIq7xc7t4PoZycc7wWKM6Atx9-HM=",
    }
)

import asyncio
import socket
from collections.abc import AsyncGenerator

import httpx2
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Database, build_engine_kwargs, build_url, get_database
from app.core.environment import ROOT_DIR, settings
from app.core.rate_limit import reset_rate_limits


def _db_available() -> bool:
    try:
        with socket.create_connection((settings.DB_HOST, settings.DB_PORT), timeout=1):
            return True
    except OSError:
        return False


DB_AVAILABLE = _db_available()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if DB_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="MariaDB de test no disponible (docker-compose.test.yml)")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


def sql_statements(script: str) -> list[str]:
    """
    Separa un script SQL en sentencias, como el cliente `mariadb`: respeta `DELIMITER`
    (necesario para stored procedures) e ignora comentarios `--` de línea completa.
    """
    statements: list[str] = []
    delimiter, buffer = ";", []
    for line in script.splitlines():
        stripped = line.strip()
        if not buffer and (not stripped or stripped.startswith("--")):
            continue
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(None, 1)[1]
            continue
        buffer.append(line)
        if stripped.endswith(delimiter):
            statement = "\n".join(buffer).strip()
            statements.append(statement[: -len(delimiter)].strip())
            buffer = []
    if "".join(buffer).strip():
        statements.append("\n".join(buffer).strip())
    return statements


async def _apply_schema() -> None:
    """BD de test desde cero: borra todas las tablas y aplica database/init + procedures."""
    engine = create_async_engine(
        build_url(), poolclass=NullPool, connect_args=build_engine_kwargs()["connect_args"]
    )
    database = ROOT_DIR / "database"
    try:
        async with engine.begin() as conn:
            tables = (await conn.exec_driver_sql("SHOW TABLES")).scalars().all()
            await conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
            for table in tables:
                await conn.exec_driver_sql(f"DROP TABLE `{table}`")
            await conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
            scripts = sorted((database / "init").glob("*.sql"))
            scripts += sorted((database / "procedures").glob("*.sql"))
            for script in scripts:
                for statement in sql_statements(script.read_text()):
                    await conn.exec_driver_sql(statement)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> None:
    """Crea el esquema una vez (fixture síncrona: corre fuera del event loop)."""
    if DB_AVAILABLE:
        asyncio.run(_apply_schema())


@pytest.fixture(scope="session")
async def app() -> AsyncGenerator[FastAPI]:
    from main import app as fastapi_app

    async with LifespanManager(fastapi_app):
        yield fastapi_app


@pytest.fixture
def v1_app(app: FastAPI) -> FastAPI:
    """Sub-app v1: los dependency_overrides se aplican aquí (donde viven las rutas)."""
    return app.state.versioned_apps["v1"]


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx2.AsyncClient]:
    transport = httpx2.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def db() -> Database:
    return get_database()


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    await reset_rate_limits()


@pytest.fixture
async def clean_users(db: Database) -> AsyncGenerator[None]:
    await db.execute("DELETE FROM users")
    yield
    await db.execute("DELETE FROM users")
