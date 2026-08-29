from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from items_api.config import Settings, get_settings
from items_api.security.lockout import (
    detect_refresh_reuse,
    mark_refresh_used,
    revoke_all_refresh_tokens,
    track_refresh_token,
    untrack_refresh_token,
)
from items_api.stores.protocol import KeyValueStore


def _refresh_key(token_hash: str) -> str:
    return f"refresh:{token_hash}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    user_id: str,
    role: str,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=cfg.access_token_minutes),
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            cfg.jwt_secret,
            algorithms=[cfg.jwt_algorithm],
            audience=cfg.jwt_audience,
            issuer=cfg.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc
    if payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )
    return payload


async def issue_refresh_token(
    store: KeyValueStore,
    user_id: str,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    ttl = cfg.refresh_token_days * 24 * 60 * 60
    await store.set(_refresh_key(token_hash), user_id, ttl=ttl)
    await track_refresh_token(store, user_id=user_id, token_hash=token_hash, settings=cfg)
    return token


async def rotate_refresh_token(
    store: KeyValueStore,
    old_token: str,
    settings: Settings | None = None,
) -> tuple[str, str]:
    cfg = settings or get_settings()
    token_hash = _hash_token(old_token)
    user_id = await store.get(_refresh_key(token_hash))
    if user_id is None:
        reused_for = await detect_refresh_reuse(store, token_hash)
        if reused_for:
            await revoke_all_refresh_tokens(store, reused_for)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "Refresh token reuse detected; all sessions revoked",
                    "code": "REFRESH_REUSE",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    await store.delete(_refresh_key(token_hash))
    await mark_refresh_used(store, user_id=user_id, token_hash=token_hash, settings=cfg)
    new_token = await issue_refresh_token(store, user_id, settings=cfg)
    return user_id, new_token


async def revoke_refresh_token(store: KeyValueStore, token: str) -> None:
    token_hash = _hash_token(token)
    user_id = await store.get(_refresh_key(token_hash))
    await store.delete(_refresh_key(token_hash))
    if user_id:
        await untrack_refresh_token(store, user_id=user_id, token_hash=token_hash)
