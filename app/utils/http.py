"""Helpers HTTP compartidos (middlewares, handlers, rate limit)."""

import logging

from starlette.types import Scope


def client_ip(scope: Scope) -> str:
    """IP del cliente. Detrás de un proxy es la real solo si uvicorn corre con
    --proxy-headers y --forwarded-allow-ips=<IP del proxy>."""
    client = scope.get("client")
    return client[0] if client else "unknown"


def log_level_for_status(status_code: int) -> int:
    """5xx → ERROR, 4xx → WARNING, resto → INFO."""
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO
