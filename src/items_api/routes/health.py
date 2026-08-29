from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from items_api.config import get_settings
from items_api.db import db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    settings = get_settings()
    if db.client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not connected",
        )
    try:
        await db.client.admin.command("ping")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB unavailable",
        ) from exc

    if settings.use_redis:
        store = request.app.state.store
        try:
            await store.set("ready:ping", "1", ttl=5)
            await store.get("ready:ping")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis unavailable",
            ) from exc

    return {"status": "ready"}
