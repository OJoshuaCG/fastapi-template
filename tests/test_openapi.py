"""Esquema OpenAPI y utilidades sin BD."""

import pytest
from fastapi import FastAPI

from app.core.environment import settings
from app.utils.response import empty, success
from tests.conftest import sql_statements


def test_openapi_keeps_envelope_fields(app: FastAPI) -> None:
    schema = app.state.versioned_apps["v1"].openapi()
    envelope = schema["components"]["schemas"]["ApiResponse_UserOut_"]
    assert set(envelope["properties"]) == {"data", "message", "pagination"}
    assert "UserOut" in schema["components"]["schemas"]


def test_envelope_json_excludes_top_level_none() -> None:
    assert success(data={"a": None}).model_dump(mode="json") == {"data": {"a": None}}
    assert empty("ok").model_dump(mode="json") == {"message": "ok"}
    assert empty().model_dump(mode="json") == {}


def test_redis_storage_uses_redis_py(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import rate_limit

    monkeypatch.setattr(settings, "RATE_LIMIT_REDIS_ENABLED", True)
    storage = rate_limit.build_storage()  # sin servidor: solo se construye
    assert type(storage).__name__ == "RedisStorage"


def test_sql_statements_supports_delimiter() -> None:
    script = """
-- comentario
CREATE TABLE t (id INT);
DELIMITER //
CREATE PROCEDURE p()
BEGIN
    SELECT 1;
    SELECT 2;
END //
DELIMITER ;
DROP TABLE t;
"""
    statements = sql_statements(script)
    assert statements[0] == "CREATE TABLE t (id INT)"
    assert statements[1].startswith("CREATE PROCEDURE p()") and "SELECT 2;" in statements[1]
    assert statements[2] == "DROP TABLE t"
