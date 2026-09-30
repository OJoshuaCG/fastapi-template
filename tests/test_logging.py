"""Filtros de logging (sin BD)."""

import logging

from app.core.logging_config import AsgiTracebackFilter


def _record(msg: str, args: tuple = (), exc: BaseException | None = None) -> logging.LogRecord:
    exc_info = (type(exc), exc, exc.__traceback__) if exc else None
    return logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1, msg, args, exc_info)


def test_asgi_traceback_dropped_only_when_already_logged() -> None:
    f = AsgiTracebackFilter()
    logged = RuntimeError("ya registrado")
    logged._app_unhandled_logged = True  # type: ignore[attr-defined]
    assert f.filter(_record("Exception in ASGI application\n", exc=logged)) is False
    assert f.filter(_record("Exception in ASGI application\n", exc=RuntimeError("nuevo"))) is True
    assert f.filter(_record("otro mensaje", exc=logged)) is True
