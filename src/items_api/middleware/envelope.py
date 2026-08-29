from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, StreamingResponse


class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        if isinstance(response, StreamingResponse) and not isinstance(response, JSONResponse):
            return response
        if response.status_code == 204:
            return response
        if response.status_code >= 400:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        try:
            payload = json.loads(body.decode() or "null")
        except json.JSONDecodeError:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        if isinstance(payload, dict) and "success" in payload:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        request_id = getattr(request.state, "request_id", None)
        if isinstance(payload, dict) and "data" in payload and "meta" in payload:
            enveloped = {
                "success": True,
                "data": payload["data"],
                "meta": payload["meta"],
            }
        else:
            enveloped = {"success": True, "data": payload}

        if request_id:
            enveloped["request_id"] = request_id

        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in {"content-length", "content-type", "set-cookie"}
        }
        wrapped = JSONResponse(
            content=enveloped,
            status_code=response.status_code,
            headers=headers,
        )
        for cookie in response.headers.getlist("set-cookie"):
            wrapped.raw_headers.append((b"set-cookie", cookie.encode("latin-1")))
        return wrapped
