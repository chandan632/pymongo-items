from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Literal

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from items_api.api.responses import error_response
from items_api.config import Settings, get_settings


def cookie_samesite(settings: Settings) -> Literal["lax", "strict", "none"]:
    value = settings.cookie_samesite.lower()
    if value in {"lax", "strict", "none"}:
        return value  # type: ignore[return-value]
    return "lax"


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    max_age = settings.refresh_token_days * 24 * 60 * 60
    kwargs: dict = {
        "key": settings.refresh_cookie_name,
        "value": token,
        "httponly": True,
        "samesite": cookie_samesite(settings),
        "secure": settings.cookie_secure_flag,
        "path": settings.refresh_cookie_path,
        "max_age": max_age,
    }
    if settings.cookie_domain_or_none:
        kwargs["domain"] = settings.cookie_domain_or_none
    response.set_cookie(**kwargs)


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    kwargs: dict = {
        "key": settings.refresh_cookie_name,
        "path": settings.refresh_cookie_path,
        "httponly": True,
        "samesite": cookie_samesite(settings),
        "secure": settings.cookie_secure_flag,
    }
    if settings.cookie_domain_or_none:
        kwargs["domain"] = settings.cookie_domain_or_none
    response.delete_cookie(**kwargs)


def set_csrf_cookie(response: Response, settings: Settings, token: str | None = None) -> str:
    value = token or secrets.token_urlsafe(32)
    max_age = settings.refresh_token_days * 24 * 60 * 60
    kwargs: dict = {
        "key": settings.csrf_cookie_name,
        "value": value,
        "httponly": False,
        "samesite": cookie_samesite(settings),
        "secure": settings.cookie_secure_flag,
        "path": "/",
        "max_age": max_age,
    }
    if settings.cookie_domain_or_none:
        kwargs["domain"] = settings.cookie_domain_or_none
    response.set_cookie(**kwargs)
    return value


def clear_csrf_cookie(response: Response, settings: Settings) -> None:
    kwargs: dict = {
        "key": settings.csrf_cookie_name,
        "path": "/",
        "samesite": cookie_samesite(settings),
        "secure": settings.cookie_secure_flag,
    }
    if settings.cookie_domain_or_none:
        kwargs["domain"] = settings.cookie_domain_or_none
    response.delete_cookie(**kwargs)


def validate_csrf(request: Request, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    if not cfg.csrf_enabled:
        return
    cookie = request.cookies.get(cfg.csrf_cookie_name)
    header = request.headers.get(cfg.csrf_header_name)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "CSRF validation failed", "code": "CSRF_FAILED"},
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        response = await call_next(request)
        if not settings.enable_security_headers:
            return response

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", settings.frame_options)
        response.headers.setdefault("Referrer-Policy", settings.referrer_policy)
        response.headers.setdefault("Permissions-Policy", settings.permissions_policy)
        response.headers.setdefault("Content-Security-Policy", settings.content_security_policy)
        response.headers.setdefault("X-XSS-Protection", "0")
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        return response


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        if not settings.csrf_enabled:
            return await call_next(request)

        path = request.url.path
        method = request.method.upper()
        protected = {
            f"{settings.api_prefix}/auth/refresh",
            f"{settings.api_prefix}/auth/logout",
            f"{settings.api_prefix}/auth/change-password",
        }
        if method == "POST" and path.rstrip("/") in {p.rstrip("/") for p in protected}:
            cookie = request.cookies.get(settings.csrf_cookie_name)
            header = request.headers.get(settings.csrf_header_name)
            if not cookie or not header or not secrets.compare_digest(cookie, header):
                from items_api.security.audit import log_security_event

                log_security_event(
                    "csrf_failure",
                    request_id=getattr(request.state, "request_id", None),
                    ip=request.client.host if request.client else None,
                    detail=path,
                )
                return error_response(
                    status_code=403,
                    code="CSRF_FAILED",
                    message="CSRF validation failed",
                    request_id=getattr(request.state, "request_id", None),
                )

        return await call_next(request)
