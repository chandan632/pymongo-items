from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, Request, status

from items_api.config import Settings, get_settings
from items_api.models.user import TokenResponse, UserCreate, UserResponse, UserRole
from items_api.repositories.user_repository import UserRepository, serialize_user, utc_now
from items_api.security.audit import log_security_event
from items_api.security.lockout import (
    assert_not_locked,
    clear_login_failures,
    record_login_failure,
    revoke_all_refresh_tokens,
)
from items_api.security.passwords import hash_password, verify_password
from items_api.security.tokens import (
    create_access_token,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from items_api.services.user_admin_service import assert_user_active


def _to_user_response(user: dict[str, Any]) -> UserResponse:
    return UserResponse(**serialize_user(user))


def client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return "unknown"
    settings = get_settings()
    host = request.client.host
    if host in settings.trusted_proxy_list:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return host


async def authenticate(
    user_repo: UserRepository,
    email: str,
    password: str,
) -> dict[str, Any]:
    user = await user_repo.find_by_email(email)
    if user is None or not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    assert_user_active(user)
    return user


async def login(
    user_repo: UserRepository,
    store: KeyValueStore,
    email: str,
    password: str,
    *,
    ip: str = "unknown",
    request_id: str | None = None,
    settings: Settings | None = None,
) -> tuple[TokenResponse, str]:
    cfg = settings or get_settings()
    await assert_not_locked(store, email=email, ip=ip)
    try:
        user = await authenticate(user_repo, email, password)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            failures = await record_login_failure(
                store, email=email, ip=ip, settings=cfg
            )
            log_security_event(
                "login_failure",
                request_id=request_id,
                email=email,
                ip=ip,
                detail=f"failures={failures}",
            )
            if failures >= cfg.login_max_failures:
                log_security_event(
                    "account_locked",
                    request_id=request_id,
                    email=email,
                    ip=ip,
                    detail=f"lock_seconds={cfg.login_lockout_seconds}",
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": (
                            "Account temporarily locked due to failed login "
                            "attempts. Try again later."
                        ),
                        "code": "ACCOUNT_LOCKED",
                    },
                ) from exc
        raise

    await clear_login_failures(store, email=email, ip=ip)
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, user["role"], settings=cfg)
    refresh_token = await issue_refresh_token(store, user_id, settings=cfg)
    log_security_event(
        "login_success",
        request_id=request_id,
        email=email,
        ip=ip,
        user_id=user_id,
    )
    return (
        TokenResponse(
            access_token=access_token,
            expires_in=cfg.access_token_minutes * 60,
            user=_to_user_response(user),
        ),
        refresh_token,
    )


async def refresh(
    user_repo: UserRepository,
    store: KeyValueStore,
    refresh_token: str,
    *,
    ip: str = "unknown",
    request_id: str | None = None,
    settings: Settings | None = None,
) -> tuple[TokenResponse, str]:
    cfg = settings or get_settings()
    try:
        user_id, new_refresh = await rotate_refresh_token(
            store, refresh_token, settings=cfg
        )
    except HTTPException as exc:
        detail = (
            exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        )
        if isinstance(detail, dict):
            code = detail.get("code", "INVALID_REFRESH")
        else:
            code = "INVALID_REFRESH"
        log_security_event(
            "refresh_failure",
            request_id=request_id,
            ip=ip,
            detail=str(code),
        )
        raise

    user = await user_repo.find_by_id(user_id)
    if user is None:
        log_security_event(
            "refresh_failure",
            request_id=request_id,
            ip=ip,
            user_id=user_id,
            detail="user_missing",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    assert_user_active(user)
    access_token = create_access_token(user_id, user["role"], settings=cfg)
    return (
        TokenResponse(
            access_token=access_token,
            expires_in=cfg.access_token_minutes * 60,
            user=_to_user_response(user),
        ),
        new_refresh,
    )


async def logout(store: KeyValueStore, refresh_token: str | None) -> None:
    if refresh_token:
        await revoke_refresh_token(store, refresh_token)


async def register_user(
    user_repo: UserRepository,
    payload: UserCreate,
) -> dict[str, Any]:
    existing = await user_repo.find_by_email(payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )
    doc = {
        "email": str(payload.email).lower(),
        "password_hash": hash_password(payload.password),
        "role": payload.role.value,
        "is_active": True,
        "created_at": utc_now(),
    }
    return await user_repo.create(doc)


async def create_admin_user(
    user_repo: UserRepository,
    email: str,
    password: str,
) -> dict[str, Any]:
    return await register_user(
        user_repo,
        UserCreate(email=email, password=password, role=UserRole.ADMIN),
    )


async def get_me(user_repo: UserRepository, user_id: str) -> dict[str, Any]:
    user = await user_repo.find_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return serialize_user(user)


async def change_password(
    user_repo: UserRepository,
    store: KeyValueStore,
    *,
    user_id: str,
    current_password: str,
    new_password: str,
    request_id: str | None = None,
) -> None:
    user = await user_repo.find_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not verify_password(current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if secrets.compare_digest(current_password, new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    updated = await user_repo.update(
        user_id,
        {"password_hash": hash_password(new_password)},
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await revoke_all_refresh_tokens(store, user_id)
    log_security_event(
        "password_changed",
        request_id=request_id,
        user_id=user_id,
        email=user.get("email"),
    )
