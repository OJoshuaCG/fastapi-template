"""
Logging de requests (middleware ASGI puro, en la app raíz).

Una línea por request: IP, método, ruta, status, duración. Nivel según el status
(5xx ERROR, 4xx WARNING, resto INFO). El detalle de errores lo loguean los exception handlers.

Nunca se loguea el body: los bodies traen contraseñas, tokens y datos personales, y
cualquier lista de "campos sensibles" termina quedándose atrás.
"""

import logging
import time
from urllib.parse import parse_qsl, urlencode

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.environment import Settings
from app.utils.dict_utils import is_sensitive_key
from app.utils.http import client_ip, log_level_for_status

logger = logging.getLogger("app.access")

_REDACTED_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}
)
_EXCLUDED_PATHS = frozenset({"/health", "/ready"})


class LoggerMiddleware:
    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500  # si la app revienta sin responder

        async def send_capturing_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_capturing_status)
        finally:
            self._log(scope, status_code, time.perf_counter() - start)

    def _log(self, scope: Scope, status_code: int, elapsed: float) -> None:
        s = self.settings
        if s.LOGGER_MIDDLEWARE_ERRORS_ONLY and status_code < 400:
            return

        level = log_level_for_status(status_code)
        parts = [
            client_ip(scope),
            f"{scope['method']} {self._display_path(scope)}",
            str(status_code),
            f"{elapsed * 1000:.1f}ms",
        ]
        if s.LOGGER_MIDDLEWARE_SHOW_QUERY_PARAMS and scope.get("query_string"):
            parts.append(f"query: {self._safe_query(scope['query_string'])}")
        if s.LOGGER_MIDDLEWARE_SHOW_HEADERS:
            headers = Headers(scope=scope)
            parts.append(
                "headers: "
                + str(
                    {
                        k: "***" if k in _REDACTED_HEADERS or is_sensitive_key(k) else v
                        for k, v in headers.items()
                    }
                )
            )
        logger.log(level, " | ".join(parts))

    def _display_path(self, scope: Scope) -> str:
        path = scope["path"]
        if self.settings.LOGGER_MIDDLEWARE_SHOW_PATH_PARAMS:
            return path
        # Plantilla de la ruta (/api/v1/users/{user_id}). Starlette escribe "route" y
        # "root_path" en el mismo scope al enrutar, así que ya están disponibles aquí.
        route = scope.get("route")
        template = getattr(route, "path", None)
        return f"{scope.get('root_path', '')}{template}" if template else path

    @staticmethod
    def _safe_query(query_string: bytes) -> str:
        pairs = parse_qsl(query_string.decode("latin-1"), keep_blank_values=True)
        return urlencode([(k, "***" if is_sensitive_key(k) else v) for k, v in pairs])
