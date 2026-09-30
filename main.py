"""
Punto de entrada.

    uv run fastapi dev            # desarrollo (reload)
    uv run fastapi run            # producción local
    uvicorn main:app --workers N  # producción (ver docker/scripts/entrypoint.sh)
"""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import http_client
from app.core.database import dispose_engine, get_database
from app.core.environment import settings
from app.core.logging_config import configure_logging
from app.core.versioned_app import create_versioned_app, telemetry_config
from app.exceptions import register_exception_handlers
from app.middleware.ContextMiddleware import ContextMiddleware
from app.middleware.LoggerMiddleware import LoggerMiddleware
from app.routes.health import router as health_router
from app.routes.v1.routes import build_v1_router

logger = logging.getLogger("app.lifespan")


async def _step(name: str, action: Callable[[], Awaitable[object]]) -> None:
    """Paso best-effort: si falla se registra y la app sigue (una dependencia caída
    durante un deploy no debe provocar un bucle de reinicios; /ready lo reporta)."""
    try:
        result = await action()
        logger.info("startup | %s: %s", name, result if result is not None else "ok")
    except Exception as e:
        logger.warning("startup | %s falló: %s: %s", name, type(e).__name__, e)


async def _close(name: str, action: Callable[[], Awaitable[object]]) -> None:
    """Paso de apagado aislado: un fallo no impide cerrar lo demás."""
    try:
        await action()
    except Exception as e:
        logger.warning("shutdown | %s falló: %s: %s", name, type(e).__name__, e)


async def _warm_up_database() -> str:
    await get_database().ping()
    return "conexión verificada"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    for warning in settings.startup_warnings:
        logger.warning("startup | %s", warning)

    await _step("base de datos", _warm_up_database)
    logger.info("startup | listo | env=%s", settings.APP_ENV)
    try:
        yield
    finally:
        # Orden: primero los clientes HTTP de los services, al final la BD
        await _close("clientes HTTP", http_client.close_all)
        await _close("base de datos", dispose_engine)
        logger.info("shutdown | completo")


def create_app() -> FastAPI:
    """La configuración sale de app.core.environment.settings (tests: variables de entorno)."""
    configure_logging(settings)

    # App raíz: sin docs propios; solo /health, /ready y el montaje de versiones
    app = FastAPI(
        title=settings.APP_NAME,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        telemetry=telemetry_config(),
    )
    register_exception_handlers(app)
    app.include_router(health_router)

    # === API v1 — docs en /api/v1/docs
    v1 = create_versioned_app("v1")
    v1.include_router(build_v1_router())
    app.mount("/api/v1", v1)

    # === API v2 (cuando sea necesaria)
    # v2 = create_versioned_app("v2")
    # v2.include_router(build_v2_router())
    # app.mount("/api/v2", v2)

    app.state.versioned_apps = {"v1": v1}

    # === Middlewares transversales (el último agregado es el más externo)
    #   Context → Logger → CORS → rutas
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    if settings.LOGGER_MIDDLEWARE_ENABLED:
        app.add_middleware(LoggerMiddleware, settings=settings)
    app.add_middleware(ContextMiddleware)
    return app


app = create_app()
