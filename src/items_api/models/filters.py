from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import Query

from items_api.models.item import ItemCategory, ItemStatus

SORTABLE_FIELDS = frozenset(
    {
        "name",
        "sku",
        "category",
        "status",
        "price",
        "quantity",
        "created_at",
        "updated_at",
    }
)


def _range_clause(
    min_value: float | int | None,
    max_value: float | int | None,
) -> dict[str, float | int]:
    clause: dict[str, float | int] = {}
    if min_value is not None:
        clause["$gte"] = min_value
    if max_value is not None:
        clause["$lte"] = max_value
    return clause


class ItemFilters:
    def __init__(
        self,
        q: Annotated[str | None, Query(max_length=200)] = None,
        category: ItemCategory | None = None,
        status: Annotated[ItemStatus | None, Query(alias="status")] = None,
        min_price: Annotated[float | None, Query(ge=0)] = None,
        max_price: Annotated[float | None, Query(ge=0)] = None,
        min_quantity: Annotated[int | None, Query(ge=0)] = None,
        max_quantity: Annotated[int | None, Query(ge=0)] = None,
    ) -> None:
        self.q = q
        self.category = category
        self.status = status
        self.min_price = min_price
        self.max_price = max_price
        self.min_quantity = min_quantity
        self.max_quantity = max_quantity

    def to_mongo_query(self) -> dict[str, Any]:
        query: dict[str, Any] = {}

        if self.q:
            pattern = re.escape(self.q)
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"sku": {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}},
            ]
        if self.category is not None:
            query["category"] = self.category.value
        if self.status is not None:
            query["status"] = self.status.value

        price = _range_clause(self.min_price, self.max_price)
        if price:
            query["price"] = price

        quantity = _range_clause(self.min_quantity, self.max_quantity)
        if quantity:
            query["quantity"] = quantity

        return query
