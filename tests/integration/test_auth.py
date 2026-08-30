from __future__ import annotations

import pytest

from tests.conftest import TEST_PASSWORD, auth_headers, csrf_headers, unwrap


def sample_item(**overrides):
    payload = {
        "name": "Test Lamp",
        "sku": "SKU-TEST-001",
        "category": "electronics",
        "status": "active",
        "price": 49.99,
        "quantity": 10,
        "description": "Test item",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_login_success(client, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    data = unwrap(response)
    assert "access_token" in data
    assert data["user"]["email"] == "admin@test.com"
    assert data["user"]["role"] == "admin"
    assert data.get("csrf_token")
    assert "refresh_token" in response.cookies
    assert "csrf_token" in response.cookies


@pytest.mark.asyncio
async def test_login_fail(client, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    err = response.json()["error"]
    assert "message" in err


@pytest.mark.asyncio
async def test_me_requires_auth(client, admin_user):
    unauth = await client.get("/api/v1/auth/me")
    assert unauth.status_code == 401

    ok = await client.get("/api/v1/auth/me", headers=auth_headers(admin_user))
    assert ok.status_code == 200
    assert unwrap(ok)["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_refresh_rotates_cookie(client, admin_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    old_refresh = login.cookies.get("refresh_token")
    assert old_refresh

    refresh = await client.post(
        "/api/v1/auth/refresh",
        headers=csrf_headers(client),
    )
    assert refresh.status_code == 200
    refresh_data = unwrap(refresh)
    assert "access_token" in refresh_data
    assert refresh_data.get("csrf_token")
    new_refresh = refresh.cookies.get("refresh_token")
    assert new_refresh
    assert new_refresh != old_refresh


@pytest.mark.asyncio
async def test_refresh_without_csrf_returns_403(client, admin_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    assert login.cookies.get("refresh_token")

    refresh = await client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 403
    assert refresh.json()["success"] is False
    assert refresh.json()["error"]["code"] == "CSRF_FAILED"


@pytest.mark.asyncio
async def test_logout_requires_csrf(client, admin_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200

    logout = await client.post(
        "/api/v1/auth/logout",
        headers=csrf_headers(client),
    )
    assert logout.status_code == 204


@pytest.mark.asyncio
async def test_register_requires_admin(client, admin_user, viewer_user, editor_user):
    payload = {
        "email": "newuser@test.com",
        "password": TEST_PASSWORD,
        "role": "viewer",
    }
    no_auth = await client.post("/api/v1/auth/register", json=payload)
    assert no_auth.status_code == 401

    as_viewer = await client.post(
        "/api/v1/auth/register",
        json=payload,
        headers=auth_headers(viewer_user),
    )
    assert as_viewer.status_code == 403

    as_editor = await client.post(
        "/api/v1/auth/register",
        json=payload,
        headers=auth_headers(editor_user),
    )
    assert as_editor.status_code == 403

    as_admin = await client.post(
        "/api/v1/auth/register",
        json=payload,
        headers=auth_headers(admin_user),
    )
    assert as_admin.status_code == 201
    assert unwrap(as_admin)["email"] == "newuser@test.com"


@pytest.mark.asyncio
async def test_viewer_cannot_seed(client, viewer_user, admin_user):
    denied = await client.post(
        "/api/v1/items/seed",
        json={"count": 2, "clear": True},
        headers=auth_headers(viewer_user),
    )
    assert denied.status_code == 403

    allowed = await client.post(
        "/api/v1/items/seed",
        json={"count": 2, "clear": True},
        headers=auth_headers(admin_user),
    )
    assert allowed.status_code == 200
    assert unwrap(allowed)["inserted"] == 2


@pytest.mark.asyncio
async def test_change_password(client, viewer_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    headers = {**auth_headers(viewer_user), **csrf_headers(client)}

    bad_current = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": "NewPass123"},
        headers={**headers, "Idempotency-Key": "pwd-1"},
    )
    assert bad_current.status_code == 400

    weak_new = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
        headers={**headers, "Idempotency-Key": "pwd-2"},
    )
    assert weak_new.status_code == 422

    ok = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "NewPass123"},
        headers={**headers, "Idempotency-Key": "pwd-3"},
    )
    assert ok.status_code == 204
    assert ok.cookies.get("refresh_token") is None

    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@test.com", "password": TEST_PASSWORD},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@test.com", "password": "NewPass123"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_requires_auth(client, viewer_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200

    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "NewPass123"},
        headers={**csrf_headers(client), "Idempotency-Key": "pwd-unauth"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_editor_can_create_viewer_cannot(client, editor_user, viewer_user):
    denied = await client.post(
        "/api/v1/items/",
        json=sample_item(),
        headers=auth_headers(viewer_user),
    )
    assert denied.status_code == 403

    created = await client.post(
        "/api/v1/items/",
        json=sample_item(),
        headers=auth_headers(editor_user),
    )
    assert created.status_code == 201
    assert unwrap(created)["sku"] == "SKU-TEST-001"
