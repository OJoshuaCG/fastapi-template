"""
Request ID + ContextVars (middleware ASGI puro, en la app raíz).

- Acepta un X-Request-ID entrante si es válido (trazas desde nginx/otros servicios),
  si no genera uno. Siempre lo devuelve en la respuesta.
- Establece los ContextVars de app.core.context y los resetea al terminar.
- Guarda el id en scope["state"] (request.state.request_id), que sobrevive aunque
  los ContextVars ya se hayan reseteado (handler de 500 de la app raíz).

ASGI puro en lugar de BaseHTTPMiddleware: sin task groups extra, sin romper streaming,
y los ContextVars que fija una dependencia son visibles para el resto del stack.
"""

import re
import secrets

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import (
    current_http_identifier,
    current_request_host,
    current_request_ip,
    current_request_method,
    current_request_route,
    current_request_user_agent,
    current_user_id,
)

_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{8,128}")


class ContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming = headers.get("x-request-id")
        request_id = (
            incoming if incoming and _VALID_REQUEST_ID.fullmatch(incoming) else secrets.token_hex(8)
        )
        scope.setdefault("state", {})["request_id"] = request_id

        client = scope.get("client")
        tokens = [
            current_http_identifier.set(request_id),
            current_request_ip.set(client[0] if client else None),
            current_request_method.set(scope["method"]),
            current_request_route.set(scope["path"]),
            current_request_host.set(headers.get("host")),
            current_request_user_agent.set(headers.get("user-agent")),
            current_user_id.set(None),
        ]
        variables = [
            current_http_identifier,
            current_request_ip,
            current_request_method,
            current_request_route,
            current_request_host,
            current_request_user_agent,
            current_user_id,
        ]

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            for var, token in zip(reversed(variables), reversed(tokens), strict=True):
                var.reset(token)
