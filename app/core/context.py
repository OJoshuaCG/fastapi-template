"""
ContextVars del ciclo de vida de una request.

Las establece `ContextMiddleware` (en la app raíz) y están disponibles en cualquier
parte del código durante la request: controllers, models, logging, handlers.
En código async viajan solas entre `await`; no hay que pasarlas como argumento.

Uso típico: auditoría (quién hizo qué, desde dónde y en qué ruta) sin pasar el request
por todas las capas. Ej. un service transversal que usan varios controllers:

    # app/services/audit_service.py
    from app.core.context import current_http_identifier, current_request_ip, current_user_id

    class AuditService:
        def __init__(self, audit: AuditModel):
            self.audit = audit

        async def record(self, action: str, detail: dict | None = None) -> None:
            await self.audit.create(
                request_id=current_http_identifier.get(),
                user_id=current_user_id.get(),
                ip=current_request_ip.get(),
                action=action,           # ej. "user.update"
                detail=detail,
            )

`current_user_id` lo debe fijar la capa de autenticación del proyecto (dependency o middleware).
"""

from contextvars import ContextVar

# Request ID (X-Request-ID entrante validado o generado)
current_http_identifier: ContextVar[str | None] = ContextVar(
    "current_http_identifier", default=None
)

current_request_ip: ContextVar[str | None] = ContextVar("current_request_ip", default=None)
current_request_method: ContextVar[str | None] = ContextVar("current_request_method", default=None)
current_request_route: ContextVar[str | None] = ContextVar("current_request_route", default=None)
current_request_host: ContextVar[str | None] = ContextVar("current_request_host", default=None)
current_request_user_agent: ContextVar[str | None] = ContextVar(
    "current_request_user_agent", default=None
)

# Para establecer desde la capa de autenticación del proyecto (dependency o middleware)
current_user_id: ContextVar[str | int | None] = ContextVar("current_user_id", default=None)


def get_request_id() -> str | None:
    return current_http_identifier.get()
