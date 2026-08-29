from __future__ import annotations

from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from items_api.api.responses import error_response
from items_api.config import get_settings


def _client_ip(request: Request) -> str:
    settings = get_settings()
    host = request.client.host if request.client else "unknown"
    if host in settings.trusted_proxy_list:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return host


def _limit_for_path(path: str) -> int:
    settings = get_settings()
    if "/export" in path:
        return settings.rate_limit_export_requests
    if "/seed" in path:
        return settings.rate_limit_seed_requests
    return settings.rate_limit_requests


def _bucket_for_path(path: str) -> str:
    if "/export" in path:
        return "export"
    if "/seed" in path:
        return "seed"
    return "default"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        store = request.app.state.store
        client_ip = _client_ip(request)
        limit = _limit_for_path(request.url.path)
        window = settings.rate_limit_window_seconds
        bucket = _bucket_for_path(request.url.path)
        key = f"rl:{client_ip}:{bucket}"

        count = await store.incr(key, ttl=window)
        remaining = max(0, limit - count)

        if count > limit:
            return error_response(
                status_code=429,
                code="RATE_LIMITED",
                message="Rate limit exceeded. Try again later.",
                request_id=getattr(request.state, "request_id", None),
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
