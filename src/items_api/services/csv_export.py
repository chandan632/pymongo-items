from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from items_api.models.filters import ItemFilters
from items_api.models.item import ItemResponse
from items_api.repositories.item_repository import ItemRepository
from items_api.services import item_service

EXPORT_FIELDS = list(ItemResponse.model_fields.keys())

_FORMULA_PREFIXES = ("=", "+", "@", "-", "\t", "\r")


def sanitize_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def parse_id_list(ids: str | None) -> list[str] | None:
    if not ids:
        return None
    return [part.strip() for part in ids.split(",") if part.strip()]


def export_row(item: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in EXPORT_FIELDS:
        value = item.get(field)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif value is None and field == "description":
            value = ""
        row[field] = sanitize_cell(value)
    return row


async def generate_csv(
    repo: ItemRepository,
    *,
    ids: list[str] | None = None,
    select_all: bool = False,
    filters: ItemFilters | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> AsyncIterator[str]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    async for item in item_service.iter_export_items(
        repo,
        ids=ids,
        select_all=select_all,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    ):
        writer.writerow(export_row(item))
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
