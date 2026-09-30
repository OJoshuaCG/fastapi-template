"""
Handlers globales de excepciones.

`register_exception_handlers(app)` se llama en la app raíz y en cada sub-app versionada,
para que todas las respuestas de error tengan el mismo formato (ver `responses.py`).
"""

import logging
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.encoding import ENCODED_ID_ERROR
from app.core.environment import APP_DIR, ROOT_DIR, settings
from app.exceptions.AppHttpException import AppHttpException
from app.exceptions.responses import DEFAULT_MESSAGES, error_response
from app.utils.dict_utils import sanitize
from app.utils.http import client_ip, log_level_for_status
from app.utils.validation_messages import format_validation_errors

logger = logging.getLogger(__name__)

# Marca en la excepción para no loguear dos veces el mismo 500: la sub-app lo maneja y
# Starlette lo relanza hacia la app raíz, que vuelve a invocar el handler genérico.
_LOGGED_MARKER = "_app_unhandled_logged"


def _request_id(request: Request) -> str | None:
    # request.state sobrevive aunque los contextvars ya se hayan reseteado
    return getattr(request.state, "request_id", None)


async def app_exception_handler(request: Request, exc: AppHttpException) -> JSONResponse:
    if exc.status_code >= 500 or settings.LOGGER_EXCEPTIONS_ENABLED:
        logger.log(
            log_level_for_status(exc.status_code),
            "%s | %s %s | %s %s | code=%s reason=%s | context=%s",
            client_ip(request.scope),
            request.method,
            request.url.path,
            exc.status_code,
            exc.message,
            exc.code,
            exc.reason,
            sanitize(exc.context),
        )
    return error_response(
        exc.status_code,
        exc.message,
        headers=dict(exc.headers) if exc.headers else None,
        code=exc.code,
        reason=exc.reason,
        errors=exc.errors,
        public=exc.public,
        context=sanitize(exc.context),
        request_id=_request_id(request),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    raw_errors = exc.errors()
    # ID público inválido en la URL (/users/abc): para el cliente el recurso no existe
    if any(
        e.get("type") == ENCODED_ID_ERROR and e.get("loc", ("",))[0] == "path" for e in raw_errors
    ):
        return error_response(404, request_id=_request_id(request))

    errors = format_validation_errors(raw_errors)
    if errors:
        first = errors[0]
        msg = f"Error de validación: {first['field']} {first['message']}"
    else:
        msg = DEFAULT_MESSAGES[422]

    if settings.LOGGER_EXCEPTIONS_ENABLED:
        logger.warning(
            "%s | %s %s | 422 | campos: %s",
            client_ip(request.scope),
            request.method,
            request.url.path,
            ", ".join(e["field"] for e in errors),
        )
    return error_response(
        422, msg, code="validation_error", errors=errors, request_id=_request_id(request)
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """404/405 de rutas, 401 de docs, 413 del límite de body, HTTPException nativo."""
    detail = exc.detail
    msg: str | None = None
    if isinstance(detail, str) and detail and not _is_default_phrase(exc.status_code, detail):
        msg = detail
    return error_response(
        exc.status_code,
        msg,
        headers=getattr(exc, "headers", None),
        request_id=_request_id(request),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Excepciones no controladas: siempre se loguean (una sola vez) con el frame del proyecto."""
    rid = _request_id(request)
    origin = _project_frame(exc)

    if not getattr(exc, _LOGGED_MARKER, False):
        try:
            setattr(exc, _LOGGED_MARKER, True)
        except AttributeError:  # excepciones con __slots__
            pass
        logger.error(
            "%s | %s %s | 500 | %s: %s | %s:%s en %s()",
            client_ip(request.scope),
            request.method,
            request.url.path,
            type(exc).__name__,
            exc,
            origin.get("file"),
            origin.get("line"),
            origin.get("function"),
            exc_info=exc,
        )

    headers = {"X-Request-ID": rid} if rid else None
    return error_response(
        500,
        headers=headers,
        context={"type_error": type(exc).__name__, "exception": str(exc)},
        loc=origin,
        request_id=rid,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppHttpException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)


# ---------------------------------------------------------------------------


# Textos en inglés que emiten FastAPI/Starlette: se reemplazan por el mensaje en español
_FRAMEWORK_DETAILS = {
    "Not authenticated",
    "Content Too Large",
    "Invalid authentication credentials",
}


def _is_default_phrase(status_code: int, detail: str) -> bool:
    from http import HTTPStatus

    if detail in _FRAMEWORK_DETAILS:
        return True
    try:
        return detail == HTTPStatus(status_code).phrase
    except ValueError:
        return False


def _is_project_file(filename: str) -> bool:
    """Frame dentro de app/ (por segmento de ruta, no por substring de la ruta)."""
    try:
        Path(filename).resolve().relative_to(APP_DIR)
    except ValueError:
        return False
    return True


def _project_frame(exc: BaseException) -> dict[str, Any]:
    """Último frame del traceback que pertenece al proyecto (no a librerías)."""
    frames = traceback.extract_tb(exc.__traceback__)
    chosen = next((f for f in reversed(frames) if _is_project_file(f.filename)), None)
    if chosen is None and frames:
        chosen = frames[-1]
    if chosen is None:
        return {"file": "unknown", "function": "unknown", "line": 0, "code": None}
    try:
        file = Path(chosen.filename).resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        file = Path(chosen.filename).name
    return {"file": file, "function": chosen.name, "line": chosen.lineno, "code": chosen.line}
