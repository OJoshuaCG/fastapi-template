"""ServiceClient (app/core/http_client.py) y el service de ejemplo, sin red (MockTransport)."""

import logging
from collections.abc import Callable

import httpx
import httpx2
import pytest
from fastapi import FastAPI

from app.core import http_client
from app.core.context import current_http_identifier
from app.core.http_client import ServiceClient, redact_url
from app.exceptions import AppHttpException
from app.services.httpbin_service import HttpbinService

Handler = Callable[[httpx.Request], httpx.Response]


class DemoService(ServiceClient):
    name = "demo"
    base_url = "https://demo.test/api"

    def headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer token-secreto"}


def service(handler: Handler, calls: list[httpx.Request] | None = None) -> DemoService:
    def recording(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return handler(request)

    return DemoService(transport=httpx.MockTransport(recording))


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_client, "_backoff", lambda attempt: 0.0)


async def test_success_sends_request_id_and_service_headers() -> None:
    calls: list[httpx.Request] = []
    svc = service(lambda r: httpx.Response(200, json={"ok": True}), calls)
    token = current_http_identifier.set("abc123")
    try:
        assert await svc.get_json("/items", params={"page": 1}) == {"ok": True}
    finally:
        current_http_identifier.reset(token)
    request = calls[0]
    assert str(request.url) == "https://demo.test/api/items?page=1"
    assert request.headers["X-Request-ID"] == "abc123"
    assert request.headers["Authorization"] == "Bearer token-secreto"


async def test_timeout_is_504() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento", request=request)

    with pytest.raises(AppHttpException) as exc:
        await service(handler).get_json("/slow")
    assert exc.value.status_code == 504 and exc.value.code == "external_service_timeout"


async def test_connection_error_is_503_after_retries() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("caído", request=request)

    with pytest.raises(AppHttpException) as exc:
        await service(handler, calls).get_json("/x")
    assert exc.value.status_code == 503 and exc.value.reason == "connection_error"
    assert len(calls) == 3  # 1 + HTTP_CLIENT_MAX_RETRIES (2)


async def test_pool_exhausted_is_503() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.PoolTimeout("pool lleno", request=request)

    with pytest.raises(AppHttpException) as exc:
        await service(handler).get_json("/x")
    assert exc.value.status_code == 503 and exc.value.reason == "pool_exhausted"


async def test_upstream_5xx_is_502_after_retries_then_recovers() -> None:
    calls: list[httpx.Request] = []
    responses = iter([httpx.Response(502), httpx.Response(200, json=[1])])
    assert await service(lambda r: next(responses), calls).get_json("/x") == [1]
    assert len(calls) == 2

    with pytest.raises(AppHttpException) as exc:
        await service(lambda r: httpx.Response(500, text="boom")).get_json("/x")
    assert exc.value.status_code == 502 and exc.value.reason == "upstream_500"


async def test_post_is_not_retried() -> None:
    calls: list[httpx.Request] = []
    with pytest.raises(AppHttpException) as exc:
        await service(lambda r: httpx.Response(503), calls).post_json("/orders", {"a": 1})
    assert exc.value.status_code == 503
    assert len(calls) == 1  # un POST reintentado podría duplicar la operación


async def test_upstream_429_propagates_retry_after() -> None:
    calls: list[httpx.Request] = []
    svc = service(lambda r: httpx.Response(429, headers={"Retry-After": "30"}), calls)
    with pytest.raises(AppHttpException) as exc:
        await svc.get_json("/x")
    assert exc.value.status_code == 503 and exc.value.headers == {"Retry-After": "30"}
    assert len(calls) == 1  # Retry-After mayor a 5s: no esperar, responder de inmediato


async def test_upstream_401_is_never_forwarded() -> None:
    with pytest.raises(AppHttpException) as exc:
        await service(lambda r: httpx.Response(401)).get_json("/x")
    assert exc.value.status_code == 502 and exc.value.reason == "upstream_auth"


async def test_allow_returns_expected_statuses() -> None:
    response = await service(lambda r: httpx.Response(404)).request("GET", "/x", allow={404})
    assert response.status_code == 404


async def test_redirects_are_not_followed() -> None:
    svc = service(lambda r: httpx.Response(302, headers={"Location": "https://evil.test"}))
    with pytest.raises(AppHttpException) as exc:
        await svc.get_json("/x")
    assert exc.value.status_code == 502


async def test_invalid_json_is_502() -> None:
    with pytest.raises(AppHttpException) as exc:
        await service(lambda r: httpx.Response(200, text="<html>")).get_json("/x")
    assert exc.value.status_code == 502 and exc.value.reason == "invalid_json"


async def test_logs_and_context_never_include_secrets(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.http_client")
    with pytest.raises(AppHttpException) as exc:
        await service(lambda r: httpx.Response(500)).get_json("/x?api_key=SECRETO")
    logs = caplog.text + repr(exc.value.context)
    assert "SECRETO" not in logs and "token-secreto" not in logs
    assert "demo | GET /x | 500" in caplog.text


async def test_missing_base_url_fails_clearly() -> None:
    class NoUrlService(ServiceClient):
        name = "no-url"

    with pytest.raises(NotImplementedError, match="base_url"):
        await NoUrlService().get_json("/x")


async def test_base_url_can_come_from_settings_via_property() -> None:
    # Caso documentado: URL distinta por entorno → property que lee settings
    class PerEnvService(ServiceClient):
        name = "per-env"

        @property
        def base_url(self) -> str:  # type: ignore[override]
            return "https://sandbox.test"

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    await PerEnvService(transport=httpx.MockTransport(handler)).get_json("/x")
    assert str(calls[0].url) == "https://sandbox.test/x"


def test_redact_url() -> None:
    assert redact_url("https://user:pw@api.test/v1/x?key=1#f") == "https://api.test/v1/x"
    assert redact_url("/orders/1?token=abc") == "/orders/1"


async def test_instance_is_shared_and_close_all_resets() -> None:
    first = DemoService.instance()
    assert DemoService.instance() is first
    assert HttpbinService.instance() is not first
    await http_client.close_all()
    assert DemoService.instance() is not first


async def test_external_route_with_overridden_service(
    client: httpx2.AsyncClient, v1_app: FastAPI
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "httpbin.org"
        rid = request.headers["X-Request-ID"]
        return httpx.Response(
            200, json={"args": dict(request.url.params), "headers": {"X-Request-Id": rid}}
        )

    fake = HttpbinService(transport=httpx.MockTransport(handler))
    v1_app.dependency_overrides[HttpbinService.instance] = lambda: fake
    try:
        ok = await client.get("/api/v1/test/external/echo", params={"q": "x"})
        failing = HttpbinService(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
        v1_app.dependency_overrides[HttpbinService.instance] = lambda: failing
        error = await client.get("/api/v1/test/external/status/401")
    finally:
        v1_app.dependency_overrides.clear()

    assert ok.status_code == 200
    assert ok.json()["data"] == {"args": {"q": "x"}, "request_id": ok.headers["X-Request-ID"]}
    assert error.status_code == 502  # el 401 del proveedor no se reenvía al cliente
    assert error.json()["detail"]["code"] == "external_service_error"
