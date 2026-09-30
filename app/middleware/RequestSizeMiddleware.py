"""
Límite de tamaño del body (middleware ASGI, en cada sub-app versionada).

- Bodies chunked / sin Content-Length: RequestBodyLimitMiddleware nativo de Starlette (≥1.6)
  cuenta los bytes a medida que llegan (sin cargar el body en memoria) y lanza un
  HTTPException 413 que el handler formatea como JSON estándar.
- Content-Length declarado mayor al límite: 413 JSON inmediato. Se revisa aquí porque el
  nativo, si el endpoint nunca lee el body, responde en texto plano. Content-Length inválido → 400.

El límite es REQUEST_MAX_SIZE_MB (mantenerlo igual a client_max_body_size de nginx).
Para un endpoint con límite distinto (ej. subida de archivos grandes), subir ambos límites.
"""

from starlette.datastructures import Headers
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.exceptions.responses import error_response


class RequestSizeMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.limited = RequestBodyLimitMiddleware(app, max_body_size=max_bytes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            if not content_length.isdigit():
                await error_response(400, "Content-Length inválido")(scope, receive, send)
                return
            if int(content_length) > self.max_bytes:
                limit_mb = self.max_bytes / (1024 * 1024)
                msg = f"El cuerpo de la solicitud supera el límite de {limit_mb:g}MB"
                await error_response(413, msg)(scope, receive, send)
                return

        await self.limited(scope, receive, send)
