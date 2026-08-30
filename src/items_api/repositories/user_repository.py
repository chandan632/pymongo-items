from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection


def utc_now() -> datetime:
    return datetime.now(UTC)


def serialize_user(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "role": doc["role"],
        "is_active": doc.get("is_active", True),
        "created_at": doc["created_at"],
    }


def parse_object_id(user_id: str) -> ObjectId | None:
    try:
        return ObjectId(user_id)
    except InvalidId:
        return None


class UserRepository:
    def __init__(self, collection: AsyncCollection) -> None:
        self.collection = collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("email", unique=True)

    async def create(self, doc: dict[str, Any]) -> dict[str, Any]:
        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize_user(doc)

    async def find_by_email(self, email: str) -> dict[str, Any] | None:
        doc = await self.collection.find_one({"email": email.lower()})
        return doc

    async def find_by_id(self, user_id: str) -> dict[str, Any] | None:
        oid = parse_object_id(user_id)
        if oid is None:
            return None
        return await self.collection.find_one({"_id": oid})

    async def update(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        oid = parse_object_id(user_id)
        if oid is None:
            return None
        doc = await self.collection.find_one_and_update(
            {"_id": oid},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return serialize_user(doc) if doc else None

    async def delete(self, user_id: str) -> bool:
        oid = parse_object_id(user_id)
        if oid is None:
            return False
        result = await self.collection.delete_one({"_id": oid})
        return result.deleted_count > 0

    async def list_users(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        docs = await (
            self.collection.find({})
            .sort([("created_at", ASCENDING), ("_id", ASCENDING)])
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )
        return [serialize_user(doc) for doc in docs]
