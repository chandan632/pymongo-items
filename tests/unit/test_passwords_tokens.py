from __future__ import annotations

import pytest
from fastapi import HTTPException

from items_api.security.passwords import hash_password, verify_password
from items_api.security.tokens import (
    create_access_token,
    decode_access_token,
    issue_refresh_token,
    rotate_refresh_token,
)
from items_api.stores.memory import MemoryStore


def test_hash_and_verify_password():
    hashed = hash_password("secret-pass")
    assert hashed != "secret-pass"
    assert verify_password("secret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip():
    token = create_access_token("user-abc", "editor")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-abc"
    assert payload["role"] == "editor"
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_refresh_rotate_with_memory_store():
    store = MemoryStore()
    token = await issue_refresh_token(store, "user-xyz")
    user_id, new_token = await rotate_refresh_token(store, token)
    assert user_id == "user-xyz"
    assert new_token != token

    with pytest.raises(HTTPException) as exc_info:
        await rotate_refresh_token(store, token)
    assert exc_info.value.status_code == 401
    detail = exc_info.value.detail
    if isinstance(detail, dict):
        assert detail.get("code") == "REFRESH_REUSE"

    with pytest.raises(HTTPException):
        await rotate_refresh_token(store, new_token)

    fresh = await issue_refresh_token(store, "user-xyz")
    user_id2, newer = await rotate_refresh_token(store, fresh)
    assert user_id2 == "user-xyz"
    assert newer != fresh


def test_validate_runtime_settings_ok_in_dev():
    from items_api.config import Settings
    from items_api.security.audit import validate_runtime_settings

    settings = Settings(
        mongo_uri="mongodb://localhost:27017",
        mongo_db_name="x",
        environment="development",
        jwt_secret="change-me-in-production-use-long-random-string",
    )
    validate_runtime_settings(settings)
