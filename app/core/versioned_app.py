"""
Factory de sub-apps versionadas (/api/v1, /api/v2...).

Reparto de responsabilidades:
    App raíz (main.py): request id, logging de requests, CORS, handlers de error,
                        lifespan (engine BD, cliente HTTP, monitor), /health, /ready.
    Sub-app versionada: rutas, documentación, límite de body y rate limit de la versión.

IMPORTANTE: Starlette NO ejecuta el lifespan de sub-apps montadas. Todo recurso con
ciclo de vida (BD, clientes, tareas) se inicia en el lifespan de la app raíz.

Los dependency_overrides también son por app: en tests se aplican sobre la sub-app
(app.state.versioned_apps["v1"]), que es donde viven las rutas.
"""

import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.routing import APIRoute
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.telemetry import TelemetryConfig

from app.core.environment import settings
from app.exceptions import register_exception_handlers
from app.middleware.RequestSizeMiddleware import RequestSizeMiddleware

_http_basic = HTTPBasic()


def telemetry_config() -> TelemetryConfig:
    """OpenTelemetry nativo de FastAPI. Sin OTEL_EXPORTER_OTLP_ENDPOINT no exporta nada."""
    if not settings.OTEL_ENABLED:
        return {
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
            "auto_configure": False,
        }
    return {"exclude": lambda scope: scope.get("path") in ("/health", "/ready")}


def _verify_docs_credentials(
    credentials: Annotated[HTTPBasicCredentials, Depends(_http_basic)],
) -> None:
    valid_user = secrets.compare_digest(credentials.username.encode(), settings.DOCS_USER.encode())
    valid_pass = secrets.compare_digest(
        credentials.password.encode(), settings.DOCS_PASSWORD.get_secret_value().encode()
    )
    if not (valid_user and valid_pass):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})


def _register_protected_docs(app: FastAPI, title: str) -> None:
    guard = [Depends(_verify_docs_credentials)]

    @app.get("/openapi.json", include_in_schema=False, dependencies=guard)
    async def openapi_schema(request: Request):
        # Igual que el handler nativo: "servers" con el root_path (/api/v1) para que
        # "Try it out" de Swagger llame a la URL correcta
        schema = dict(app.openapi())
        root_path = request.scope.get("root_path", "").rstrip("/")
        if root_path and "servers" not in schema:
            schema["servers"] = [{"url": root_path}]
        return schema

    @app.get("/docs", include_in_schema=False, dependencies=guard)
    async def swagger():
        return get_swagger_ui_html(openapi_url="openapi.json", title=f"{title} - Swagger")

    @app.get("/redoc", include_in_schema=False, dependencies=guard)
    async def redoc():
        return get_redoc_html(openapi_url="openapi.json", title=f"{title} - ReDoc")


def _operation_id(route: APIRoute) -> str:
    # Nombres limpios para clientes generados desde OpenAPI: "Users-get_user"
    return f"{route.tags[0]}-{route.name}" if route.tags else route.name


def create_versioned_app(version: str) -> FastAPI:
    """
    Crea la sub-app de una versión de la API.

    Args:
        version: "v1", "v2"...

    Uso (main.py):
        v1 = create_versioned_app("v1")
        v1.include_router(v1_router)
        app.mount("/api/v1", v1)
    """
    title = f"{settings.APP_NAME} {version.upper()}"
    public_docs = bool(settings.docs_enabled) and not settings.DOCS_PASSWORD_ENABLED

    versioned = FastAPI(
        title=title,
        version=version,
        docs_url="/docs" if public_docs else None,
        redoc_url="/redoc" if public_docs else None,
        openapi_url="/openapi.json" if public_docs else None,
        generate_unique_id_function=_operation_id,
        telemetry=telemetry_config(),
    )
    if settings.docs_enabled and settings.DOCS_PASSWORD_ENABLED:
        _register_protected_docs(versioned, title)

    register_exception_handlers(versioned)

    versioned.add_middleware(RequestSizeMiddleware, max_bytes=settings.request_max_bytes)
    return versioned
