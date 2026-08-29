from __future__ import annotations

import pytest

from items_api.config import get_settings


@pytest.mark.asyncio
async def test_rate_limit_exceeded(client):
    settings = get_settings()
    original = settings.rate_limit_requests
    settings.rate_limit_requests = 2
    try:
        first = await client.get("/api/v1/health")
        second = await client.get("/api/v1/health")
        third = await client.get("/api/v1/health")
        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        body = third.json()
        assert body["success"] is False
        assert body["error"]["code"] == "RATE_LIMITED"
        assert "message" in body["error"]
    finally:
        settings.rate_limit_requests = original
