from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from items_api.api.deps import get_store, get_user_repo, require_role
from items_api.config import get_settings
from items_api.middleware.security import (
    clear_csrf_cookie,
    clear_refresh_cookie,
    set_csrf_cookie,
    set_refresh_cookie,
)
from items_api.models.user import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserRole,
)
from items_api.repositories.user_repository import UserRepository
from items_api.services import auth_service
from items_api.stores.protocol import KeyValueStore

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    request: Request,
    response: Response,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    store: Annotated[KeyValueStore, Depends(get_store)],
):
    settings = get_settings()
    token_response, refresh_token = await auth_service.login(
        user_repo,
        store,
        payload.email,
        payload.password,
        ip=auth_service.client_ip(request),
        request_id=getattr(request.state, "request_id", None),
        settings=settings,
    )
    set_refresh_cookie(response, refresh_token, settings)
    set_csrf_cookie(response, settings)
    return token_response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    store: Annotated[KeyValueStore, Depends(get_store)],
):
    settings = get_settings()
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    token_response, new_refresh = await auth_service.refresh(
        user_repo,
        store,
        refresh_token,
        ip=auth_service.client_ip(request),
        request_id=getattr(request.state, "request_id", None),
        settings=settings,
    )
    set_refresh_cookie(response, new_refresh, settings)
    set_csrf_cookie(response, settings)
    return token_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    store: Annotated[KeyValueStore, Depends(get_store)],
):
    settings = get_settings()
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    await auth_service.logout(store, refresh_token)
    clear_refresh_cookie(response, settings)
    clear_csrf_cookie(response, settings)


@router.get("/me", response_model=UserResponse)
async def me(
    user: Annotated[dict, Depends(require_role(UserRole.VIEWER))],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
):
    return await auth_service.get_me(user_repo, user["id"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    _admin: Annotated[dict, Depends(require_role(UserRole.ADMIN))],
):
    return await auth_service.register_user(user_repo, payload)
