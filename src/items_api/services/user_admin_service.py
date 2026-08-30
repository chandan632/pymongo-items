from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from items_api.config import Settings, get_settings
from items_api.models.user import AdminUserCreate, UserAdminUpdate, UserRole
from items_api.repositories.user_repository import UserRepository, serialize_user, utc_now
from items_api.security.audit import log_security_event
from items_api.security.lockout import revoke_all_refresh_tokens
from items_api.security.passwords import hash_password
from items_api.stores.protocol import KeyValueStore


def _assert_not_self(admin_id: str, target_id: str, action: str) -> None:
    if admin_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot {action} your own account",
        )


async def _get_user_or_404(user_repo: UserRepository, user_id: str) -> dict[str, Any]:
    user = await user_repo.find_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def list_users(user_repo: UserRepository) -> list[dict[str, Any]]:
    return await user_repo.list_users(limit=500)


async def create_user_admin(
    user_repo: UserRepository,
    payload: AdminUserCreate,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    existing = await user_repo.find_by_email(payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )
    doc = {
        "email": str(payload.email).lower(),
        "password_hash": hash_password(cfg.default_user_password),
        "role": payload.role.value,
        "is_active": True,
        "created_at": utc_now(),
    }
    return await user_repo.create(doc)


async def update_user_admin(
    user_repo: UserRepository,
    store: KeyValueStore,
    *,
    admin_id: str,
    user_id: str,
    payload: UserAdminUpdate,
    request_id: str | None = None,
) -> dict[str, Any]:
    _assert_not_self(admin_id, user_id, "modify")
    user = await _get_user_or_404(user_repo, user_id)

    updates: dict[str, Any] = {}
    if payload.role is not None:
        updates["role"] = payload.role.value
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    role_changed = (
        payload.role is not None and payload.role.value != user.get("role")
    )
    deactivate = payload.is_active is False
    # Force re-login: revoke refresh sessions when privileges or access change.
    if role_changed or deactivate:
        await revoke_all_refresh_tokens(store, user_id)

    updated = await user_repo.update(user_id, updates)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    log_security_event(
        "user_admin_update",
        request_id=request_id,
        user_id=admin_id,
        detail=f"target={user_id} role={updates.get('role', user['role'])} "
        f"is_active={updates.get('is_active', user.get('is_active', True))}",
    )
    return updated


async def delete_user_admin(
    user_repo: UserRepository,
    store: KeyValueStore,
    *,
    admin_id: str,
    user_id: str,
    request_id: str | None = None,
) -> None:
    _assert_not_self(admin_id, user_id, "delete")
    await _get_user_or_404(user_repo, user_id)
    await revoke_all_refresh_tokens(store, user_id)
    deleted = await user_repo.delete(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    log_security_event(
        "user_admin_delete",
        request_id=request_id,
        user_id=admin_id,
        detail=f"target={user_id}",
    )


async def reset_user_password_admin(
    user_repo: UserRepository,
    store: KeyValueStore,
    *,
    admin_id: str,
    user_id: str,
    request_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    await _get_user_or_404(user_repo, user_id)
    updated = await user_repo.update(
        user_id,
        {"password_hash": hash_password(cfg.default_user_password)},
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await revoke_all_refresh_tokens(store, user_id)
    log_security_event(
        "user_password_reset",
        request_id=request_id,
        user_id=admin_id,
        detail=f"target={user_id}",
    )
    return updated


def assert_user_active(user: dict[str, Any]) -> None:
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
