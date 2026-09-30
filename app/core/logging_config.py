"""
Configuración de logging (una sola vez, al crear la app).

En cada módulo:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Operación completada")   # el request_id se agrega solo

- Formato text (default) o JSON (LOG_FORMAT=json) para agregadores (Loki, ELK, Datadog).
- Cada línea lleva el request_id de la request en curso (ContextVar), o "-".
- Se descarta el "Exception in ASGI application" de uvicorn cuando el error ya fue
  registrado por nuestro handler de 500 (evita tracebacks duplicados).
"""

import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Any

from app.core.context import current_http_identifier, current_user_id
from app.core.environment import Settings

_configured = False

# Atributos estándar de LogRecord: lo que no esté aquí vino por `extra=` y va al JSON
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_http_identifier.get() or "-"
        if not hasattr(record, "user_id"):
            record.user_id = current_user_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        user_id = getattr(record, "user_id", None)
        if user_id is not None:
            payload["user_id"] = user_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and key != "user_id":
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class AsgiTracebackFilter(logging.Filter):
    """Descarta el traceback de uvicorn para excepciones que nuestro handler ya registró."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn emite "Exception in ASGI application\n" (con salto de línea)
        if not record.exc_info or record.getMessage().strip() != "Exception in ASGI application":
            return True
        exc = record.exc_info[1]
        # CancelledError / KeyboardInterrupt no son Exception: se conservan
        return not (isinstance(exc, Exception) and getattr(exc, "_app_unhandled_logged", False))


def configure_logging(settings: Settings) -> None:
    global _configured
    if _configured:
        return

    formatter = (
        {"()": JsonFormatter}
        if settings.LOG_FORMAT == "json"
        else {"format": "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s] %(message)s"}
    )
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_context": {"()": RequestContextFilter},
            },
            "formatters": {"default": formatter},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_context"],
                },
            },
            "loggers": {
                "app": {
                    "handlers": ["console"],
                    "level": settings.LOGGER_LEVEL,
                    "propagate": False,
                },
            },
            # Librerías (sqlalchemy, httpx, limits...): mismo formato, solo WARNING o más
            "root": {"handlers": ["console"], "level": "WARNING"},
        }
    )
    # Los loggers de uvicorn se configuran antes de importar la app: solo se les agrega
    # el filtro (reconfigurarlos con dictConfig les quitaría sus handlers)
    logging.getLogger("uvicorn.error").addFilter(AsgiTracebackFilter())
    _configured = True
