from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault(
    "MONGO_URI",
    "mongodb://items:items_secret@localhost:27017/?authSource=admin",
)
os.environ.setdefault("MONGO_DB_NAME", "items_db_test")
os.environ.setdefault("USE_REDIS", "false")
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-tests-only-32b")
os.environ.setdefault("ALLOW_SEED", "true")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("CSRF_ENABLED", "true")
os.environ.setdefault("COOKIE_SECURE", "false")

TEST_PASSWORD = "Password123"

from items_api.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def test_db() -> AsyncIterator[dict[str, Any]]:
    from items_api.db import close_db, connect_db, get_database
    from items_api.repositories.item_repository import ItemRepository
    from items_api.repositories.user_repository import UserRepository

    get_settings.cache_clear()
    await connect_db()
    settings = get_settings()
    database = get_database()
    await database["items"].delete_many({})
    await database["users"].delete_many({})
    item_repo = ItemRepository(database["items"])
    user_repo = UserRepository(database["users"])
    await item_repo.ensure_indexes()
    await user_repo.ensure_indexes()
    yield {
        "db": database,
        "settings": settings,
        "item_repo": item_repo,
        "user_repo": user_repo,
    }
    await database.client.drop_database(settings.mongo_db_name)
    await close_db()


@pytest.fixture
async def client(test_db: dict[str, Any]) -> AsyncIterator[AsyncClient]:
    from items_api.main import app
    from items_api.stores import create_store

    settings = test_db["settings"]
    store = create_store(settings)
    app.state.store = store
    app.state.settings = settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def auth_headers(user: dict[str, Any]) -> dict[str, str]:
    from items_api.security.tokens import create_access_token

    user_id = user.get("id") or str(user["_id"])
    role = user["role"].value if hasattr(user["role"], "value") else user["role"]
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_user(test_db: dict[str, Any]) -> dict[str, Any]:
    from items_api.services import auth_service

    return await auth_service.create_admin_user(
        test_db["user_repo"],
        "admin@test.com",
        TEST_PASSWORD,
    )


@pytest.fixture
async def editor_user(test_db: dict[str, Any]) -> dict[str, Any]:
    from items_api.models.user import UserCreate, UserRole
    from items_api.services import auth_service

    return await auth_service.register_user(
        test_db["user_repo"],
        UserCreate(email="editor@test.com", password=TEST_PASSWORD, role=UserRole.EDITOR),
    )


@pytest.fixture
async def viewer_user(test_db: dict[str, Any]) -> dict[str, Any]:
    from items_api.models.user import UserCreate, UserRole
    from items_api.services import auth_service

    return await auth_service.register_user(
        test_db["user_repo"],
        UserCreate(email="viewer@test.com", password=TEST_PASSWORD, role=UserRole.VIEWER),
    )


def unwrap(response) -> Any:
    body = response.json()
    if isinstance(body, dict) and body.get("success") is True and "data" in body:
        return body["data"]
    if isinstance(body, dict) and body.get("success") is False:
        return body.get("error")
    return body


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    if not token:
        return {}
    return {"X-CSRF-Token": token}
