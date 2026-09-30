"""
Serializador único de errores.

Todas las respuestas de error (handlers de excepciones y middlewares) salen de aquí,
con un solo formato:

    {
      "detail": {
        "msg":        "texto para el usuario",               # siempre
        "type":       "NotFound",                            # siempre, derivado del status
        "code":       "user_not_found",                      # opcional, estable
        "reason":     "pool_exhausted",                      # opcional, estable
        "errors":     [{"field", "message", "type"}],        # opcional (validación)
        "...":        claves de `public`,                    # opcional
        "request_id": "a1b2c3...",                           # siempre que exista
        "context":    {...},                                 # SOLO development
        "loc":        {"file","function","line","code"}      # SOLO development
      }
    }
"""

from http import HTTPStatus
from typing import Any

from fastapi.responses import JSONResponse

from app.core.context import get_request_id
from app.core.environment import settings

# `type` se deriva de la frase HTTP (404 → "NotFound"); solo el 422 usa un nombre propio
_TYPE_BY_STATUS = {422: "ValidationError"}

DEFAULT_MESSAGES = {
    400: "Solicitud inválida",
    401: "No autorizado",
    403: "Acceso denegado",
    404: "Recurso no encontrado",
    405: "Método no permitido",
    409: "Conflicto con el estado actual del recurso",
    413: "El cuerpo de la solicitud excede el tamaño permitido",
    415: "Tipo de contenido no soportado",
    422: "Error de validación en los datos enviados",
    429: "Demasiadas solicitudes, intenta más tarde",
    500: "Error interno del servidor",
    502: "Un servicio externo respondió con un error",
    503: "Servicio no disponible temporalmente",
    504: "El servicio tardó demasiado en responder",
}

_RESERVED = {"msg", "type", "code", "reason", "errors", "request_id", "context", "loc"}


def error_type(status_code: int) -> str:
    if status_code in _TYPE_BY_STATUS:
        return _TYPE_BY_STATUS[status_code]
    try:
        return HTTPStatus(status_code).phrase.title().replace(" ", "").replace("-", "")
    except ValueError:
        return "Error"


def build_error_body(
    status_code: int,
    msg: str | None = None,
    *,
    code: str | None = None,
    reason: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    public: dict[str, Any] | None = None,
    context: Any = None,
    loc: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "msg": msg or DEFAULT_MESSAGES.get(status_code, "Error"),
        "type": error_type(status_code),
    }
    if code:
        detail["code"] = code
    if reason:
        detail["reason"] = reason
    if errors:
        detail["errors"] = errors
    if public:
        detail.update({k: v for k, v in public.items() if k not in _RESERVED})

    rid = request_id or get_request_id()
    if rid:
        detail["request_id"] = rid

    if settings.is_development:
        if context is not None:
            detail["context"] = context
        if loc:
            detail["loc"] = loc
    return {"detail": detail}


def error_response(
    status_code: int,
    msg: str | None = None,
    *,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> JSONResponse:
    """Respuesta JSON de error lista para devolver desde un handler o middleware ASGI."""
    body = build_error_body(status_code, msg, **fields)
    if status_code in (204, 304):
        return JSONResponse(status_code=status_code, content=None, headers=headers)
    return JSONResponse(status_code=status_code, content=body, headers=headers)
