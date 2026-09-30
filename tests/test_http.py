"""Capa HTTP: formato de errores, request id, CORS, límites, logging. No requieren BD."""

import logging

import httpx2
import pytest


async def test_request_id_generated_and_echoed(client: httpx2.AsyncClient) -> None:
    generated = await client.get("/api/v1/test/ping")
    assert len(generated.headers["x-request-id"]) == 16

    echoed = await client.get("/api/v1/test/ping", headers={"X-Request-ID": "trace-abc-123"})
    assert echoed.headers["x-request-id"] == "trace-abc-123"

    invalid = await client.get("/api/v1/test/ping", headers={"X-Request-ID": "bad id\n"})
    assert invalid.headers["x-request-id"] != "bad id\n"


@pytest.mark.parametrize(
    ("method", "path", "status", "error_type"),
    [
        ("GET", "/no-existe", 404, "NotFound"),
        ("GET", "/api/v1/no-existe", 404, "NotFound"),
        ("POST", "/api/v1/test/ping", 405, "MethodNotAllowed"),
        ("PUT", "/api/v1/test/custom-error", 400, "BadRequest"),
    ],
)
async def test_errors_share_one_format(
    client: httpx2.AsyncClient, method: str, path: str, status: int, error_type: str
) -> None:
    resp = await client.request(method, path)
    assert resp.status_code == status
    detail = resp.json()["detail"]
    assert detail["type"] == error_type
    assert isinstance(detail["msg"], str) and detail["msg"]
    assert detail["request_id"] == resp.headers["x-request-id"]
    assert "context" not in detail  # solo en development


async def test_validation_error_in_spanish_without_input(client: httpx2.AsyncClient) -> None:
    resp = await client.get("/api/v1/test/paginated", params={"page": 0, "size": "abc"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "validation_error"
    fields = {e["field"]: e for e in detail["errors"]}
    assert fields["page"]["message"] == "debe ser mayor o igual a 1"
    assert fields["size"]["message"] == "debe ser un número entero"
    assert all("input" not in e for e in detail["errors"])


async def test_unhandled_error_is_500_logged_once(
    client: httpx2.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app"):
        resp = await client.post("/api/v1/test/unhandled-error")
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail["type"] == "InternalServerError"
    assert detail["request_id"] == resp.headers["x-request-id"]
    assert "RuntimeError" not in resp.text  # nada interno fuera de development
    handler_logs = [r for r in caplog.records if r.name == "app.exceptions.HandlerExceptions"]
    assert len(handler_logs) == 1


async def test_body_limit_is_413_json(client: httpx2.AsyncClient) -> None:
    big = b"x" * (11 * 1024 * 1024)  # REQUEST_MAX_SIZE_MB=10
    resp = await client.post(
        "/api/v1/test/upload", content=big, headers={"content-type": "application/octet-stream"}
    )
    assert resp.status_code == 413
    assert resp.json()["detail"]["type"] == "ContentTooLarge"


async def test_body_limit_applies_to_chunked_bodies(client: httpx2.AsyncClient) -> None:
    async def chunks():
        for _ in range(12):
            yield b"x" * (1024 * 1024)

    resp = await client.post(
        "/api/v1/users", content=chunks(), headers={"content-type": "application/json"}
    )
    assert resp.status_code == 413


async def test_login_rate_limit_with_retry_after(client: httpx2.AsyncClient) -> None:
    statuses = [(await client.post("/api/v1/test/login")).status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]  # RATE_LIMIT_LOGIN=3/minute
    limited = await client.post("/api/v1/test/login")
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["detail"]["code"] == "rate_limited"


async def test_streaming_response_passes_through_middlewares(client: httpx2.AsyncClient) -> None:
    resp = await client.get("/api/v1/test/stream")
    assert resp.status_code == 200
    assert resp.text == "chunk 0\nchunk 1\nchunk 2\n"


async def test_cors(client: httpx2.AsyncClient) -> None:
    preflight = {"Origin": "https://ok.example", "Access-Control-Request-Method": "POST"}
    ok = await client.options("/api/v1/test/ping", headers=preflight)
    assert ok.headers["access-control-allow-origin"] == "https://ok.example"

    denied = await client.options(
        "/api/v1/test/ping", headers={**preflight, "Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in denied.headers


async def test_access_log_never_contains_secrets(
    client: httpx2.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.post(
            "/api/v1/users?token=abc123",
            json={"username": "x", "email": "bad", "password": "SuperSecreta!"},
        )
    text = caplog.text
    assert "SuperSecreta!" not in text
    assert "abc123" not in text
    assert "token=%2A%2A%2A" in text


async def test_health_and_ready(client: httpx2.AsyncClient) -> None:
    assert (await client.get("/health")).json()["status"] == "ok"
