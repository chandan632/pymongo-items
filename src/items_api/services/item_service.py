from __future__ import annotations

from collections.abc import AsyncIterator
from math import ceil
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from items_api.config import get_settings
from items_api.models.filters import SORTABLE_FIELDS, ItemFilters
from items_api.models.item import (
    BulkAction,
    BulkActionRequest,
    ItemCreate,
    ItemUpdate,
)
from items_api.repositories.item_repository import ItemRepository, serialize, utc_now


def validate_list_params(
    sort_by: str,
    sort_order: str,
    min_price: float | None,
    max_price: float | None,
    min_quantity: int | None,
    max_quantity: int | None,
) -> None:
    if sort_by not in SORTABLE_FIELDS:
        allowed = ", ".join(sorted(SORTABLE_FIELDS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by. Allowed: {allowed}",
        )
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_order must be 'asc' or 'desc'",
        )
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_price cannot be greater than max_price",
        )
    if min_quantity is not None and max_quantity is not None and min_quantity > max_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_quantity cannot be greater than max_quantity",
        )


def page_meta(total: int, page: int, page_size: int) -> tuple[int, dict[str, int]]:
    total_pages = ceil(total / page_size) if total else 0
    safe_page = min(page, total_pages) if total and page > total_pages else page
    return safe_page, {
        "page": safe_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _parse_object_ids(ids: list[str]) -> list[ObjectId]:
    object_ids: list[ObjectId] = []
    for item_id in ids:
        try:
            object_ids.append(ObjectId(item_id))
        except InvalidId as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid item id: {item_id}",
            ) from exc
    return object_ids


def _filters_to_query(
    *,
    q: str | None = None,
    category=None,
    status_filter=None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_quantity: int | None = None,
    max_quantity: int | None = None,
) -> dict[str, Any]:
    return ItemFilters(
        q=q,
        category=category,
        status=status_filter,
        min_price=min_price,
        max_price=max_price,
        min_quantity=min_quantity,
        max_quantity=max_quantity,
    ).to_mongo_query()


def resolve_bulk_filter(payload: BulkActionRequest) -> dict[str, Any]:
    if payload.select_all:
        query = _filters_to_query(
            q=payload.q,
            category=payload.category,
            status_filter=payload.status,
            min_price=payload.min_price,
            max_price=payload.max_price,
            min_quantity=payload.min_quantity,
            max_quantity=payload.max_quantity,
        )
        if payload.exclude_ids:
            query["_id"] = {"$nin": _parse_object_ids(payload.exclude_ids)}
        if query == {} and payload.action == BulkAction.DELETE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refusing bulk delete with empty filter",
            )
        return query

    if payload.ids:
        return {"_id": {"$in": _parse_object_ids(payload.ids)}}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Provide ids or set select_all=true",
    )


async def create_item(repo: ItemRepository, item: ItemCreate) -> dict[str, Any]:
    now = utc_now()
    doc = {**item.model_dump(mode="json"), "created_at": now, "updated_at": now}
    try:
        return await repo.create(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item with SKU '{item.sku}' already exists",
        ) from exc


async def get_item(repo: ItemRepository, item_id: str) -> dict[str, Any]:
    from items_api.repositories.item_repository import parse_object_id

    if parse_object_id(item_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item id")
    item = await repo.find_by_id(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


async def list_items(
    repo: ItemRepository,
    filters: ItemFilters,
    *,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any]:
    validate_list_params(
        sort_by,
        sort_order,
        filters.min_price,
        filters.max_price,
        filters.min_quantity,
        filters.max_quantity,
    )
    query = filters.to_mongo_query()
    total = await repo.estimated_count() if not query else await repo.count(query)
    safe_page, meta = page_meta(total, page, page_size)
    data = await repo.find_page(
        query,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=(safe_page - 1) * page_size,
        limit=page_size,
    )
    return {"data": data, "meta": meta}


async def update_item(
    repo: ItemRepository,
    item_id: str,
    payload: ItemUpdate,
) -> dict[str, Any]:
    from items_api.repositories.item_repository import parse_object_id

    if parse_object_id(item_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item id")
    updates = payload.model_dump(exclude_unset=True, mode="json")
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    updates["updated_at"] = utc_now()
    try:
        item = await repo.update(item_id, updates)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU already exists",
        ) from exc
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


async def delete_item(repo: ItemRepository, item_id: str) -> None:
    from items_api.repositories.item_repository import parse_object_id

    if parse_object_id(item_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item id")
    deleted = await repo.delete(item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")


async def bulk_action(
    repo: ItemRepository,
    payload: BulkActionRequest,
) -> dict[str, Any]:
    query = resolve_bulk_filter(payload)
    matched = await repo.count(query)

    if payload.action == BulkAction.DELETE:
        modified = await repo.delete_many(query)
        return {"matched": matched, "modified": modified, "action": BulkAction.DELETE}

    if payload.action == BulkAction.SET_STATUS:
        if payload.status_value is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="status_value is required for set_status",
            )
        modified = await repo.update_many(
            query,
            {"$set": {"status": payload.status_value.value, "updated_at": utc_now()}},
        )
        return {"matched": matched, "modified": modified, "action": BulkAction.SET_STATUS}

    if payload.action == BulkAction.ADJUST_QUANTITY:
        if payload.quantity_delta is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="quantity_delta is required for adjust_quantity",
            )
        modified = await repo.adjust_quantity_atomic(query, payload.quantity_delta)
        return {
            "matched": matched,
            "modified": modified,
            "action": BulkAction.ADJUST_QUANTITY,
        }

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported bulk action")


async def iter_export_items(
    repo: ItemRepository,
    *,
    ids: list[str] | None = None,
    select_all: bool = False,
    filters: ItemFilters | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> AsyncIterator[dict[str, Any]]:
    if sort_by not in SORTABLE_FIELDS:
        allowed = ", ".join(sorted(SORTABLE_FIELDS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by. Allowed: {allowed}",
        )
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_order must be 'asc' or 'desc'",
        )

    if ids and not select_all:
        query: dict[str, Any] = {"_id": {"$in": _parse_object_ids(ids)}}
    else:
        filters = filters or ItemFilters()
        query = filters.to_mongo_query()

    settings = get_settings()
    max_rows = settings.export_max_rows
    direction = 1 if sort_order == "asc" else -1
    cursor = repo.collection.find(query).sort([(sort_by, direction), ("_id", 1)])

    count = 0
    async for doc in cursor:
        if count >= max_rows:
            break
        yield serialize(doc)
        count += 1
