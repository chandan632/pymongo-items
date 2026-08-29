from __future__ import annotations

import asyncio

import pytest

from items_api.stores.memory import MemoryStore


@pytest.mark.asyncio
async def test_set_get_delete():
    store = MemoryStore()
    await store.set("k", "v")
    assert await store.get("k") == "v"
    await store.delete("k")
    assert await store.get("k") is None


@pytest.mark.asyncio
async def test_ttl_expires():
    store = MemoryStore()
    await store.set("temp", "1", ttl=1)
    assert await store.get("temp") == "1"
    await asyncio.sleep(1.1)
    assert await store.get("temp") is None


@pytest.mark.asyncio
async def test_set_nx():
    store = MemoryStore()
    assert await store.set_nx("lock", "1", ttl=60) is True
    assert await store.set_nx("lock", "2", ttl=60) is False
    assert await store.get("lock") == "1"


@pytest.mark.asyncio
async def test_incr():
    store = MemoryStore()
    assert await store.incr("counter", ttl=60) == 1
    assert await store.incr("counter", ttl=60) == 2
    assert await store.incr("counter") == 3
