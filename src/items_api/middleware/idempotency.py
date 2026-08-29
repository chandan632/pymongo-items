from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import Callable
from time import monotonic

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.responses import Response as StarletteResponse

from items_api.config import get_settings

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_IN_FLIGHT_TTL = 30
_WAIT_SECONDS = 0.05
_WAIT_ATTEMPTS = 20


def _cache_key(fingerprint: str) -> str:
    return f"idem:resp:{fingerprint}"


def _lock_key(fingerprint: str) -> str:
    return f"idem:lock:{fingerprint}"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in MUTATING_METHODS:
            return await call_next(request)

        key = request.headers.get("Idempotency-Key")
        if not key:
            return await call_next(request)

        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)

        body_text = body.decode("utf-8", errors="replace")
        fingerprint = hashlib.sha256(
            f"{request.method}:{request.url.path}:{key}:{body_text}".encode()
        ).hexdigest()

        store = request.app.state.store
        settings = get_settings()
        ttl = settings.idempotency_ttl_seconds

        cached = await store.get(_cache_key(fingerprint))
        if cached is not None:
            return self._replay(cached)

        acquired = await store.set_nx(_lock_key(fingerprint), "1", ttl=_IN_FLIGHT_TTL)
        if not acquired:
            for _ in range(_WAIT_ATTEMPTS):
                await asyncio.sleep(_WAIT_SECONDS)
                cached = await store.get(_cache_key(fingerprint))
                if cached is not None:
                    return self._replay(cached)
            return JSONResponse(
                status_code=409,
                content={
                    "error": {"message": "Request with this Idempotency-Key is already in progress"}
                },
            )

        started = monotonic()
        try:
            response = await call_next(request)
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk if isinstance(chunk, bytes) else chunk.encode()

            store_headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() in {"content-type", "location"}
            }

            if 200 <= response.status_code < 500:
                payload = json.dumps(
                    {
                        "status_code": response.status_code,
                        "body": base64.b64encode(response_body).decode("ascii"),
                        "headers": store_headers,
                        "media_type": response.media_type,
                        "created": started,
                    }
                )
                await store.set(_cache_key(fingerprint), payload, ttl=ttl)

            return StarletteResponse(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        finally:
            await store.delete(_lock_key(fingerprint))

    @staticmethod
    def _replay(cached: str) -> Response:
        data = json.loads(cached)
        body = base64.b64decode(data["body"])
        headers = {**data.get("headers", {}), "X-Idempotent-Replay": "true"}
        return StarletteResponse(
            content=body,
            status_code=data["status_code"],
            headers=headers,
            media_type=data.get("media_type") or headers.get("content-type", "application/json"),
        )
