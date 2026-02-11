from contextvars import ContextVar
from typing import Optional

current_user_id: ContextVar[Optional[int]] = ContextVar("current_user_id", default=None)

current_request_ip: ContextVar[Optional[str]] = ContextVar("current_request_ip", default=None)
current_request_method: ContextVar[Optional[str]] = ContextVar("current_request_method", default=None)
current_request_route: ContextVar[Optional[str]] = ContextVar("current_request_route", default=None)

current_request_client_host: ContextVar[Optional[str]] = ContextVar("current_request_client_host", default=None)
current_request_host: ContextVar[Optional[str]] = ContextVar("current_request_host", default=None)
current_request_user_agent: ContextVar[Optional[str]] = ContextVar("current_request_user_agent", default=None)

current_http_identifier: ContextVar[Optional[str]] = ContextVar("current_http_identifier", default=None)