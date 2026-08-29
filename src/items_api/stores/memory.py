import time


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    def _expired(self, expires_at: float | None) -> bool:
        return expires_at is not None and time.monotonic() >= expires_at

    def _get_entry(self, key: str) -> tuple[str, float | None] | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._expired(expires_at):
            del self._data[key]
            return None
        return value, expires_at

    async def get(self, key: str) -> str | None:
        entry = self._get_entry(key)
        return entry[0] if entry else None

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + ttl if ttl is not None else None
        self._data[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def set_nx(self, key: str, value: str, ttl: int | None = None) -> bool:
        if self._get_entry(key) is not None:
            return False
        await self.set(key, value, ttl=ttl)
        return True

    async def incr(self, key: str, ttl: int | None = None) -> int:
        entry = self._get_entry(key)
        if entry is None:
            value = 1
            expires_at = time.monotonic() + ttl if ttl is not None else None
        else:
            value = int(entry[0]) + 1
            expires_at = entry[1]
            if expires_at is None and ttl is not None:
                expires_at = time.monotonic() + ttl
        self._data[key] = (str(value), expires_at)
        return value
