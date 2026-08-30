from __future__ import annotations

import pytest

from tests.conftest import TEST_PASSWORD, auth_headers, unwrap


@pytest.mark.asyncio
async def test_list_users_requires_admin(client, admin_user, editor_user, viewer_user):
    denied = await client.get("/api/v1/auth/users/", headers=auth_headers(viewer_user))
    assert denied.status_code == 403

    denied_editor = await client.get(
        "/api/v1/auth/users/",
        headers=auth_headers(editor_user),
    )
    assert denied_editor.status_code == 403

    ok = await client.get("/api/v1/auth/users/", headers=auth_headers(admin_user))
    assert ok.status_code == 200
    users = unwrap(ok)
    assert len(users) >= 3


@pytest.mark.asyncio
async def test_admin_create_user_with_default_password(client, admin_user):
    created = await client.post(
        "/api/v1/auth/users/",
        json={"email": "managed@test.com", "role": "viewer"},
        headers=auth_headers(admin_user),
    )
    assert created.status_code == 201
    body = unwrap(created)
    assert body["email"] == "managed@test.com"
    assert body["role"] == "viewer"
    assert body["is_active"] is True

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "managed@test.com", "password": "password"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_admin_update_role_and_deactivate(client, admin_user, editor_user):
    headers = auth_headers(admin_user)
    target = unwrap(
        await client.post(
            "/api/v1/auth/users/",
            json={"email": "toggle@test.com", "role": "editor"},
            headers=headers,
        )
    )

    updated = await client.patch(
        f"/api/v1/auth/users/{target['id']}",
        json={"role": "viewer", "is_active": False},
        headers=headers,
    )
    assert updated.status_code == 200
    body = unwrap(updated)
    assert body["role"] == "viewer"
    assert body["is_active"] is False

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "toggle@test.com", "password": "password"},
    )
    assert login.status_code == 403


@pytest.mark.asyncio
async def test_admin_reset_password(client, admin_user):
    headers = auth_headers(admin_user)
    target = unwrap(
        await client.post(
            "/api/v1/auth/users/",
            json={"email": "resetme@test.com", "role": "viewer"},
            headers=headers,
        )
    )

    reset = await client.post(
        f"/api/v1/auth/users/{target['id']}/reset-password",
        headers=headers,
    )
    assert reset.status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "resetme@test.com", "password": "password"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(client, admin_user):
    response = await client.delete(
        f"/api/v1/auth/users/{admin_user['id']}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_role_change_invalidates_existing_access_token(client, admin_user, editor_user):
    from tests.conftest import csrf_headers

    admin_headers = auth_headers(admin_user)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "editor@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    editor_token = unwrap(login)["access_token"]
    editor_headers = {"Authorization": f"Bearer {editor_token}"}

    before = await client.post(
        "/api/v1/items/",
        json={
            "name": "Before Demotion",
            "sku": "SKU-ROLE-1",
            "category": "home",
            "status": "active",
            "price": 10,
            "quantity": 1,
        },
        headers={**editor_headers, "Idempotency-Key": "role-before"},
    )
    assert before.status_code == 201

    demote = await client.patch(
        f"/api/v1/auth/users/{editor_user['id']}",
        json={"role": "viewer"},
        headers=admin_headers,
    )
    assert demote.status_code == 200
    assert unwrap(demote)["role"] == "viewer"

    after = await client.get("/api/v1/auth/me", headers=editor_headers)
    assert after.status_code == 401
    err = after.json()["error"]
    assert err["code"] == "PRIVILEGES_CHANGED"

    refresh = await client.post(
        "/api/v1/auth/refresh",
        headers=csrf_headers(client),
    )
    assert refresh.status_code == 401


@pytest.mark.asyncio
async def test_deactivate_invalidates_existing_access_token(client, admin_user, editor_user):
    from tests.conftest import csrf_headers

    admin_headers = auth_headers(admin_user)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "editor@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    editor_token = unwrap(login)["access_token"]
    editor_headers = {"Authorization": f"Bearer {editor_token}"}

    me = await client.get("/api/v1/auth/me", headers=editor_headers)
    assert me.status_code == 200

    deactivate = await client.patch(
        f"/api/v1/auth/users/{editor_user['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate.status_code == 200
    assert unwrap(deactivate)["is_active"] is False

    after = await client.get("/api/v1/auth/me", headers=editor_headers)
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "ACCOUNT_INACTIVE"

    refresh = await client.post(
        "/api/v1/auth/refresh",
        headers=csrf_headers(client),
    )
    assert refresh.status_code == 401


@pytest.mark.asyncio
async def test_admin_delete_user(client, admin_user):
    headers = auth_headers(admin_user)
    target = unwrap(
        await client.post(
            "/api/v1/auth/users/",
            json={"email": "delete-me@test.com", "role": "viewer"},
            headers=headers,
        )
    )

    deleted = await client.delete(
        f"/api/v1/auth/users/{target['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204

    users = unwrap(await client.get("/api/v1/auth/users/", headers=headers))
    assert all(user["id"] != target["id"] for user in users)
