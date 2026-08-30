from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException, status

from items_api.config import Settings, get_settings
from items_api.stores.protocol import KeyValueStore


def _fail_key(email: str, ip: str) -> str:
    digest = hashlib.sha256(f"{email.lower().strip()}|{ip}".encode()).hexdigest()[:32]
    return f"login_fail:{digest}"


def _lock_key(email: str, ip: str) -> str:
    digest = hashlib.sha256(f"{email.lower().strip()}|{ip}".encode()).hexdigest()[:32]
    return f"login_lock:{digest}"


async def assert_not_locked(
    store: KeyValueStore,
    *,
    email: str,
    ip: str,
) -> None:
    if await store.get(_lock_key(email, ip)) is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": (
                    "Account temporarily locked due to failed login attempts. "
                    "Try again later."
                ),
                "code": "ACCOUNT_LOCKED",
            },
        )


async def record_login_failure(
    store: KeyValueStore,
    *,
    email: str,
    ip: str,
    settings: Settings | None = None,
) -> int:
    cfg = settings or get_settings()
    window = cfg.login_lockout_window_seconds
    key = _fail_key(email, ip)
    count = await store.incr(key, ttl=window)
    if count >= cfg.login_max_failures:
        await store.set(_lock_key(email, ip), "1", ttl=cfg.login_lockout_seconds)
        await store.delete(key)
    return count


async def clear_login_failures(
    store: KeyValueStore,
    *,
    email: str,
    ip: str,
) -> None:
    await store.delete(_fail_key(email, ip))
    await store.delete(_lock_key(email, ip))


def _user_tokens_key(user_id: str) -> str:
    return f"refresh_tokens:{user_id}"


def _used_token_key(token_hash: str) -> str:
    return f"refresh_used:{token_hash}"


async def _load_user_hashes(store: KeyValueStore, user_id: str) -> list[str]:
    raw = await store.get(_user_tokens_key(user_id))
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


async def _save_user_hashes(
    store: KeyValueStore,
    user_id: str,
    hashes: list[str],
    ttl: int,
) -> None:
    await store.set(_user_tokens_key(user_id), json.dumps(hashes), ttl=ttl)


async def track_refresh_token(
    store: KeyValueStore,
    *,
    user_id: str,
    token_hash: str,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    ttl = cfg.refresh_token_days * 24 * 60 * 60
    hashes = await _load_user_hashes(store, user_id)
    if token_hash not in hashes:
        hashes.append(token_hash)
    await _save_user_hashes(store, user_id, hashes[-20:], ttl)


async def untrack_refresh_token(
    store: KeyValueStore,
    *,
    user_id: str,
    token_hash: str,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    ttl = cfg.refresh_token_days * 24 * 60 * 60
    hashes = [h for h in await _load_user_hashes(store, user_id) if h != token_hash]
    if hashes:
        await _save_user_hashes(store, user_id, hashes, ttl)
    else:
        await store.delete(_user_tokens_key(user_id))


async def mark_refresh_used(
    store: KeyValueStore,
    *,
    user_id: str,
    token_hash: str,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    ttl = cfg.refresh_token_days * 24 * 60 * 60
    await store.set(_used_token_key(token_hash), user_id, ttl=ttl)
    await untrack_refresh_token(store, user_id=user_id, token_hash=token_hash, settings=cfg)


async def revoke_all_refresh_tokens(
    store: KeyValueStore,
    user_id: str,
) -> int:
    hashes = await _load_user_hashes(store, user_id)
    for token_hash in hashes:
        await store.delete(f"refresh:{token_hash}")
        await store.delete(_used_token_key(token_hash))
        await store.delete(f"refresh_grace:{token_hash}")
    await store.delete(_user_tokens_key(user_id))
    return len(hashes)


async def detect_refresh_reuse(
    store: KeyValueStore,
    token_hash: str,
) -> str | None:
    return await store.get(_used_token_key(token_hash))
