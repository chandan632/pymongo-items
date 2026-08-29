from __future__ import annotations

import pytest

from tests.conftest import TEST_PASSWORD, csrf_headers


@pytest.mark.asyncio
async def test_login_lockout_after_failures(client, admin_user):
    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": "WrongPass1"},
        )
        assert response.status_code in {401, 429}

    locked = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": TEST_PASSWORD},
    )
    assert locked.status_code == 429
    body = locked.json()
    assert body["success"] is False
    assert body["error"]["code"] == "ACCOUNT_LOCKED"


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_sessions(client, admin_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    old_refresh = login.cookies.get("refresh_token")

    first = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert first.status_code == 200
    client.cookies.set("refresh_token", old_refresh)
    reuse = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert reuse.status_code == 401
    err = reuse.json()["error"]
    assert err["code"] in {"REFRESH_REUSE", "UNAUTHORIZED"}

@pytest.mark.asyncio
async def test_production_settings_reject_weak_secret():
    from items_api.config import Settings
    from items_api.security.audit import validate_runtime_settings

    settings = Settings(
        mongo_uri="mongodb://localhost:27017",
        mongo_db_name="x",
        environment="production",
        jwt_secret="change-me-in-production-use-long-random-string",
        allow_seed=False,
        cookie_secure=True,
        cors_origins="https://app.example.com",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_runtime_settings(settings)
