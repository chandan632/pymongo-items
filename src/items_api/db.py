from pymongo import AsyncMongoClient

from items_api.config import get_settings


class Database:
    client: AsyncMongoClient | None = None


db = Database()


async def connect_db() -> None:
    settings = get_settings()
    db.client = AsyncMongoClient(
        settings.mongo_uri,
        maxPoolSize=settings.mongo_max_pool_size,
        minPoolSize=settings.mongo_min_pool_size,
        maxIdleTimeMS=settings.mongo_max_idle_time_ms,
        serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
    )


async def close_db() -> None:
    if db.client:
        await db.client.close()
        db.client = None


def get_database():
    settings = get_settings()
    if db.client is None:
        raise RuntimeError("Database not connected")
    return db.client[settings.mongo_db_name]
