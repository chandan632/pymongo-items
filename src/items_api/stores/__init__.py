from items_api.config import Settings
from items_api.stores.memory import MemoryStore
from items_api.stores.protocol import KeyValueStore
from items_api.stores.redis_store import RedisStore


def create_store(settings: Settings) -> KeyValueStore:
    if settings.use_redis:
        return RedisStore(settings.redis_url)
    return MemoryStore()


__all__ = ["KeyValueStore", "MemoryStore", "RedisStore", "create_store"]
