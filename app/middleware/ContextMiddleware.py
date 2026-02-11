import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.context import (
    current_http_identifier,
    current_request_client_host,
    current_request_host,
    current_request_ip,
    current_request_method,
    current_request_route,
    current_request_user_agent,
)


class ContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Generar un ID único para la solicitud (Correlation ID)
        request_id = secrets.token_hex(8)

        # 2. Establecer variables de contexto
        # Usamos tokens para limpiar el contexto si fuera necesario (buena práctica en frameworks complejos,
        # aunque en FastAPI por request se limpia solo al acabar la tarea, pero es explícito)
        token_id = current_http_identifier.set(request_id)
        token_ip = current_request_ip.set(
            request.client.host if request.client else "unknown"
        )
        token_method = current_request_method.set(request.method)
        token_route = current_request_route.set(request.url.path)
        token_client_host = current_request_client_host.set(
            request.client.host if request.client else None
        )
        token_host = current_request_host.set(request.url.hostname)
        token_user_agent = current_request_user_agent.set(
            request.headers.get("user-agent")
        )

        # Inyectar el ID en el request state para acceso fácil si es necesario
        request.state.request_id = request_id

        try:
            response = await call_next(request)

            # 3. Inyectar el header X-Request-ID en la respuesta para trazabilidad
            response.headers["X-Request-ID"] = request_id

            return response

        finally:
            # 4. Limpieza de ContextVars (Opcional pero recomendado para evitar fugas en algunos entornos de testing o pooling)
            current_http_identifier.reset(token_id)
            current_request_ip.reset(token_ip)
            current_request_method.reset(token_method)
            current_request_route.reset(token_route)
            current_request_client_host.reset(token_client_host)
            current_request_host.reset(token_host)
            current_request_user_agent.reset(token_user_agent)
