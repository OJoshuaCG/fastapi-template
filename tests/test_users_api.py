"""CRUD de usuarios de punta a punta (HTTP → controller → model → MariaDB)."""

import httpx2
import pytest
from fastapi import FastAPI

from app.controllers.user_controller import get_user_controller
from app.core.database import get_database
from app.core.encoding import encode_id

pytestmark = pytest.mark.db

NEW_USER = {"username": "ana", "email": "ana@example.com", "password": "secreto123"}


async def test_crud_flow(client: httpx2.AsyncClient, clean_users) -> None:
    created = await client.post("/api/v1/users", json=NEW_USER)
    assert created.status_code == 201, created.text
    user = created.json()["data"]
    assert user["username"] == "ana"
    assert "encrypted_password" not in user and "password" not in user

    assert isinstance(user["id"], str) and not user["id"].isdigit()  # ID público, no el int
    got = await client.get(f"/api/v1/users/{user['id']}")
    assert got.status_code == 200 and got.json()["data"]["email"] == "ana@example.com"

    updated = await client.patch(f"/api/v1/users/{user['id']}", json={"full_name": "Ana Pérez"})
    assert updated.status_code == 200 and updated.json()["data"]["full_name"] == "Ana Pérez"

    listed = await client.get("/api/v1/users", params={"page": 1, "size": 10})
    body = listed.json()
    assert body["pagination"]["total"] == 1 and len(body["data"]) == 1

    deleted = await client.delete(f"/api/v1/users/{user['id']}")
    assert deleted.status_code == 200
    assert (await client.get(f"/api/v1/users/{user['id']}")).status_code == 404


async def test_duplicate_user_is_409(client: httpx2.AsyncClient, clean_users) -> None:
    assert (await client.post("/api/v1/users", json=NEW_USER)).status_code == 201
    dup = await client.post("/api/v1/users", json=NEW_USER)
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "user_conflict"


async def test_update_same_values_is_not_404(client: httpx2.AsyncClient, clean_users) -> None:
    user = (await client.post("/api/v1/users", json=NEW_USER)).json()["data"]
    again = await client.patch(f"/api/v1/users/{user['id']}", json={"email": user["email"]})
    assert again.status_code == 200


async def test_unknown_fields_are_rejected(client: httpx2.AsyncClient) -> None:
    resp = await client.patch(f"/api/v1/users/{encode_id(1)}", json={"id = 1; --": "x"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "validation_error"


async def test_controller_can_be_overridden(client: httpx2.AsyncClient, v1_app: FastAPI) -> None:
    class FakeController:
        async def get_user(self, user_id: int) -> dict:
            return {
                "id": user_id,
                "username": "fake",
                "email": "fake@example.com",
                "full_name": None,
                "notes": None,
                "is_active": True,
                "is_superuser": False,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }

    v1_app.dependency_overrides[get_user_controller] = FakeController
    try:
        resp = await client.get(f"/api/v1/users/{encode_id(99)}")
    finally:
        v1_app.dependency_overrides.clear()
    assert resp.status_code == 200 and resp.json()["data"]["username"] == "fake"
    assert resp.json()["data"]["id"] == encode_id(99)  # el int del controller sale codificado


async def test_ready_reports_database(client: httpx2.AsyncClient, app: FastAPI) -> None:
    ok = await client.get("/ready")
    assert ok.status_code == 200 and ok.json()["checks"]["database"] == "up"

    class DownDatabase:
        async def ping(self) -> None:
            raise ConnectionError("down")

    app.dependency_overrides[get_database] = DownDatabase
    try:
        down = await client.get("/ready")
    finally:
        app.dependency_overrides.clear()
    assert down.status_code == 503 and down.json()["checks"]["database"] == "down"
    assert (await client.get("/health")).status_code == 200  # liveness no depende de la BD


async def test_patch_null_on_not_null_column_is_422(client: httpx2.AsyncClient) -> None:
    for payload in ({"email": None}, {"is_active": None}):
        resp = await client.patch(f"/api/v1/users/{encode_id(1)}", json=payload)
        assert resp.status_code == 422, payload


async def test_invalid_public_id_is_404(client: httpx2.AsyncClient) -> None:
    # Inválido, int crudo o forma no canónica: para el cliente el recurso no existe
    for raw in ("abc", "15", encode_id(15) + "x"):
        resp = await client.get(f"/api/v1/users/{raw}")
        assert resp.status_code == 404, raw
        assert resp.json()["detail"]["type"] == "NotFound"
