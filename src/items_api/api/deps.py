from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from items_api.db import get_database
from items_api.models.user import UserRole
from items_api.repositories.item_repository import ItemRepository
from items_api.repositories.user_repository import UserRepository, serialize_user
from items_api.security.tokens import decode_access_token
from items_api.stores.protocol import KeyValueStore

_bearer = HTTPBearer(auto_error=True)

ROLE_RANK = {
    UserRole.VIEWER.value: 1,
    UserRole.EDITOR.value: 2,
    UserRole.ADMIN.value: 3,
    "viewer": 1,
    "editor": 2,
    "admin": 3,
}


def get_store(request: Request) -> KeyValueStore:
    return request.app.state.store


def get_item_repo() -> ItemRepository:
    return ItemRepository(get_database()["items"])


def get_user_repo() -> UserRepository:
    return UserRepository(get_database()["users"])


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> dict:
    payload = decode_access_token(credentials.credentials)
    user = await user_repo.find_by_id(payload["sub"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Account is inactive. Please sign in again.",
                "code": "ACCOUNT_INACTIVE",
            },
        )

    token_role = payload.get("role")
    db_role = user.get("role")
    if token_role is not None and db_role is not None and token_role != db_role:
        from items_api.security.audit import log_security_event

        log_security_event(
            "privileges_changed",
            request_id=getattr(request.state, "request_id", None),
            ip=request.client.host if request.client else None,
            user_id=str(user.get("_id")),
            detail=f"token_role={token_role} db_role={db_role}",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Your access level changed. Please sign in again.",
                "code": "PRIVILEGES_CHANGED",
            },
        )

    return serialize_user(user)


def require_role(*roles: str | UserRole) -> Callable:
    required_rank = min(
        ROLE_RANK[role.value if isinstance(role, UserRole) else role] for role in roles
    )

    async def dependency(
        request: Request,
        user: Annotated[dict, Depends(get_current_user)],
    ) -> dict:
        user_rank = ROLE_RANK.get(user["role"], 0)
        if user_rank < required_rank:
            from items_api.security.audit import log_security_event

            log_security_event(
                "access_denied",
                request_id=getattr(request.state, "request_id", None),
                ip=request.client.host if request.client else None,
                user_id=user.get("id"),
                detail=(
                    f"required_rank={required_rank} user_rank={user_rank} "
                    f"path={request.url.path}"
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return dependency
