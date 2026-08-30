from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from items_api.api.deps import get_store, get_user_repo, require_role
from items_api.config import get_settings
from items_api.models.user import AdminUserCreate, UserAdminUpdate, UserResponse, UserRole
from items_api.repositories.user_repository import UserRepository
from items_api.services import user_admin_service
from items_api.services.auth_service import client_ip
from items_api.stores.protocol import KeyValueStore

router = APIRouter(prefix="/auth/users", tags=["Users"])


@router.get("/", response_model=list[UserResponse])
async def list_users(
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    _admin: Annotated[dict, Depends(require_role(UserRole.ADMIN))],
):
    return await user_admin_service.list_users(user_repo)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    admin: Annotated[dict, Depends(require_role(UserRole.ADMIN))],
    request: Request,
):
    user = await user_admin_service.create_user_admin(
        user_repo,
        payload,
        settings=get_settings(),
    )
    from items_api.security.audit import log_security_event

    log_security_event(
        "user_admin_create",
        request_id=getattr(request.state, "request_id", None),
        user_id=admin["id"],
        detail=f"target={user['id']} email={user['email']} role={user['role']}",
    )
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserAdminUpdate,
    request: Request,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    store: Annotated[KeyValueStore, Depends(get_store)],
    admin: Annotated[dict, Depends(require_role(UserRole.ADMIN))],
):
    return await user_admin_service.update_user_admin(
        user_repo,
        store,
        admin_id=admin["id"],
        user_id=user_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    request: Request,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    store: Annotated[KeyValueStore, Depends(get_store)],
    admin: Annotated[dict, Depends(require_role(UserRole.ADMIN))],
):
    await user_admin_service.delete_user_admin(
        user_repo,
        store,
        admin_id=admin["id"],
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/{user_id}/reset-password", response_model=UserResponse)
async def reset_user_password(
    user_id: str,
    request: Request,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    store: Annotated[KeyValueStore, Depends(get_store)],
    admin: Annotated[dict, Depends(require_role(UserRole.ADMIN))],
):
    return await user_admin_service.reset_user_password_admin(
        user_repo,
        store,
        admin_id=admin["id"],
        user_id=user_id,
        request_id=getattr(request.state, "request_id", None),
        settings=get_settings(),
    )
