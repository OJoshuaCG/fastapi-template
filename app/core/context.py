from contextvars import ContextVar

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)

current_request_ip: ContextVar[str | None] = ContextVar(
    "current_request_ip", default=None
)
current_request_method: ContextVar[str | None] = ContextVar(
    "current_request_method", default=None
)
current_request_route: ContextVar[str | None] = ContextVar(
    "current_request_route", default=None
)

current_request_client_host: ContextVar[str | None] = ContextVar(
    "current_request_client_host", default=None
)
current_request_host: ContextVar[str | None] = ContextVar(
    "current_request_host", default=None
)
current_request_user_agent: ContextVar[str | None] = ContextVar(
    "current_request_user_agent", default=None
)

current_http_identifier: ContextVar[str | None] = ContextVar(
    "current_http_identifier", default=None
)
