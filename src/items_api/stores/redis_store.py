from redis.asyncio import Redis


class RedisStore:
    def __init__(self, redis_url: str) -> None:
        self._redis: Redis = Redis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        value = await self._redis.get(key)
        if value is None:
            return None
        return value if isinstance(value, str) else value.decode()

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl is not None:
            await self._redis.set(key, value, ex=ttl)
        else:
            await self._redis.set(key, value)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def set_nx(self, key: str, value: str, ttl: int | None = None) -> bool:
        ok = await self._redis.set(key, value, nx=True, ex=ttl)
        return bool(ok)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        value = await self._redis.incr(key)
        if ttl is not None and value == 1:
            await self._redis.expire(key, ttl)
        return int(value)

    async def aclose(self) -> None:
        await self._redis.aclose()
