from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId
from fastapi import HTTPException

from items_api.services.cursor import (
    build_cursor_filter,
    decode_cursor,
    encode_cursor,
)


def test_encode_decode_cursor_round_trip_datetime():
    doc = {
        "_id": ObjectId(),
        "created_at": datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    }
    token = encode_cursor(sort_by="created_at", sort_order="desc", doc=doc)
    value, item_id = decode_cursor(
        token,
        expected_sort_by="created_at",
        expected_sort_order="desc",
    )
    assert value == doc["created_at"]
    assert item_id == doc["_id"]


def test_decode_cursor_rejects_sort_mismatch():
    doc = {"_id": ObjectId(), "price": 12.5}
    token = encode_cursor(sort_by="price", sort_order="asc", doc=doc)
    with pytest.raises(HTTPException) as exc:
        decode_cursor(token, expected_sort_by="price", expected_sort_order="desc")
    assert exc.value.status_code == 400


def test_build_cursor_filter_desc():
    item_id = ObjectId()
    clause = build_cursor_filter("price", "desc", 10.0, item_id)
    assert clause == {
        "$or": [
            {"price": {"$lt": 10.0}},
            {"price": 10.0, "_id": {"$gt": item_id}},
        ]
    }


def test_build_cursor_filter_asc():
    item_id = ObjectId()
    clause = build_cursor_filter("price", "asc", 10.0, item_id)
    assert clause == {
        "$or": [
            {"price": {"$gt": 10.0}},
            {"price": 10.0, "_id": {"$gt": item_id}},
        ]
    }
