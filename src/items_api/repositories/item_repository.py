from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

SKU_INDEX_PATTERN = r"^SKU-\d{6}$"


def utc_now() -> datetime:
    return datetime.now(UTC)


def serialize(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "sku": doc["sku"],
        "category": doc["category"],
        "status": doc["status"],
        "price": doc["price"],
        "quantity": doc["quantity"],
        "description": doc.get("description"),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


def parse_object_id(item_id: str) -> ObjectId | None:
    try:
        return ObjectId(item_id)
    except InvalidId:
        return None


class ItemRepository:
    def __init__(self, collection: AsyncCollection) -> None:
        self.collection = collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("sku", unique=True)
        await self.collection.create_index([("category", ASCENDING), ("status", ASCENDING)])
        await self.collection.create_index([("created_at", DESCENDING)])
        await self.collection.create_index([("name", ASCENDING)])

    async def create(self, doc: dict[str, Any]) -> dict[str, Any]:
        result = await self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize(doc)

    async def find_by_id(self, item_id: str) -> dict[str, Any] | None:
        oid = parse_object_id(item_id)
        if oid is None:
            return None
        doc = await self.collection.find_one({"_id": oid})
        return serialize(doc) if doc else None

    async def update(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        oid = parse_object_id(item_id)
        if oid is None:
            return None
        doc = await self.collection.find_one_and_update(
            {"_id": oid},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return serialize(doc) if doc else None

    async def delete(self, item_id: str) -> bool:
        oid = parse_object_id(item_id)
        if oid is None:
            return False
        result = await self.collection.delete_one({"_id": oid})
        return result.deleted_count > 0

    async def count(self, query: dict[str, Any]) -> int:
        return await self.collection.count_documents(query)

    async def estimated_count(self) -> int:
        return await self.collection.estimated_document_count()

    async def find_page(
        self,
        query: dict[str, Any],
        *,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        direction = ASCENDING if sort_order == "asc" else DESCENDING
        docs = await (
            self.collection.find(query)
            .sort([(sort_by, direction), ("_id", ASCENDING)])
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )
        return [serialize(doc) for doc in docs]

    async def delete_many(self, query: dict[str, Any]) -> int:
        result = await self.collection.delete_many(query)
        return result.deleted_count

    async def update_many(self, query: dict[str, Any], update: dict[str, Any]) -> int:
        result = await self.collection.update_many(query, update)
        return result.modified_count

    async def insert_many(self, docs: list[dict[str, Any]]) -> int:
        if not docs:
            return 0
        result = await self.collection.insert_many(docs, ordered=False)
        return len(result.inserted_ids)

    async def adjust_quantity_atomic(self, query: dict[str, Any], delta: int) -> int:
        now = utc_now()
        result = await self.collection.update_many(
            query,
            [
                {
                    "$set": {
                        "quantity": {"$max": [0, {"$add": ["$quantity", delta]}]},
                        "updated_at": now,
                    }
                }
            ],
        )
        return result.modified_count

    async def max_sku_index(self) -> int:
        pipeline: list[Mapping[str, Any]] = [
            {"$match": {"sku": {"$regex": SKU_INDEX_PATTERN}}},
            {
                "$project": {
                    "n": {
                        "$toInt": {
                            "$arrayElemAt": [{"$split": ["$sku", "-"]}, 1],
                        }
                    }
                }
            },
            {"$group": {"_id": None, "max_n": {"$max": "$n"}}},
        ]
        cursor = await self.collection.aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        if not docs or docs[0].get("max_n") is None:
            return 0
        return int(docs[0]["max_n"])
