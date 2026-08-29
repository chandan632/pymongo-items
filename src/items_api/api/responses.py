from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def request_id_of(request: Any) -> str | None:
    return getattr(getattr(request, "state", None), "request_id", None)


def success_body(
    data: Any = None,
    *,
    meta: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"success": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    if request_id:
        body["request_id"] = request_id
    return body


def error_body(
    *,
    code: str,
    message: str,
    details: Any = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    body: dict[str, Any] = {"success": False, "error": error}
    if request_id:
        body["request_id"] = request_id
    return body


def success_response(
    data: Any = None,
    *,
    status_code: int = 200,
    meta: dict[str, Any] | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=success_body(data, meta=meta, request_id=request_id),
        headers=headers,
    )


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_body(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        ),
        headers=headers,
    )


def http_status_to_code(status_code: int) -> str:
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    return mapping.get(status_code, f"HTTP_{status_code}")
