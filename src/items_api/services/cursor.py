from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

DATETIME_FIELDS = frozenset({"created_at", "updated_at"})
INT_FIELDS = frozenset({"quantity"})
FLOAT_FIELDS = frozenset({"price"})


def _encode_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _decode_value(sort_by: str, value: Any) -> Any:
    if sort_by in DATETIME_FIELDS:
        if not isinstance(value, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor sort value",
            )
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    if sort_by in INT_FIELDS:
        return int(value)
    if sort_by in FLOAT_FIELDS:
        return float(value)
    return value


def encode_cursor(*, sort_by: str, sort_order: str, doc: dict[str, Any]) -> str:
    payload = {
        "s": sort_by,
        "o": sort_order,
        "v": _encode_value(doc[sort_by]),
        "id": str(doc["_id"]),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
    return raw.decode().rstrip("=")


def decode_cursor(
    cursor: str,
    *,
    expected_sort_by: str,
    expected_sort_order: str,
) -> tuple[Any, ObjectId]:
    padding = "=" * (-len(cursor) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode())
        sort_by = payload["s"]
        sort_order = payload["o"]
        sort_value = _decode_value(sort_by, payload["v"])
        item_id = ObjectId(payload["id"])
    except (KeyError, ValueError, InvalidId, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc

    if sort_by != expected_sort_by or sort_order != expected_sort_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cursor does not match current sort parameters",
        )
    return sort_value, item_id


def build_cursor_filter(
    sort_by: str,
    sort_order: str,
    sort_value: Any,
    item_id: ObjectId,
) -> dict[str, Any]:
    if sort_order == "desc":
        primary_op = "$lt"
    else:
        primary_op = "$gt"

    return {
        "$or": [
            {sort_by: {primary_op: sort_value}},
            {sort_by: sort_value, "_id": {"$gt": item_id}},
        ]
    }
