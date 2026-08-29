from __future__ import annotations

import re

from items_api.models.filters import ItemFilters
from items_api.models.item import ItemCategory, ItemStatus
from items_api.services.csv_export import sanitize_cell
from items_api.services.item_service import page_meta


def test_range_via_to_mongo_query():
    query = ItemFilters(
        min_price=10,
        max_price=20,
        min_quantity=1,
        max_quantity=5,
    ).to_mongo_query()
    assert query["price"] == {"$gte": 10, "$lte": 20}
    assert query["quantity"] == {"$gte": 1, "$lte": 5}

    min_only = ItemFilters(min_price=5).to_mongo_query()
    assert min_only["price"] == {"$gte": 5}


def test_search_escapes_regex_metacharacters():
    raw = "(a+)+"
    query = ItemFilters(q=raw).to_mongo_query()
    pattern = query["$or"][0]["name"]["$regex"]
    assert pattern == re.escape(raw)
    assert pattern != raw


def test_to_mongo_query_enums_and_search():
    query = ItemFilters(
        q="lamp",
        category=ItemCategory.ELECTRONICS,
        status=ItemStatus.ACTIVE,
        min_price=10,
        max_price=100,
    ).to_mongo_query()
    assert query["category"] == "electronics"
    assert query["status"] == "active"
    assert query["price"] == {"$gte": 10, "$lte": 100}
    assert len(query["$or"]) == 3


def test_page_meta_empty():
    page, meta = page_meta(0, 1, 20)
    assert page == 1
    assert meta["total"] == 0
    assert meta["total_pages"] == 0


def test_page_meta_clamps_overflow():
    page, meta = page_meta(45, 99, 20)
    assert page == 3
    assert meta["total_pages"] == 3


def test_sanitize_cell_formula_injection():
    assert sanitize_cell("=1+1") == "'=1+1"
    assert sanitize_cell("+cmd") == "'+cmd"
    assert sanitize_cell("@SUM(A1)") == "'@SUM(A1)"
    assert sanitize_cell("-1") == "'-1"
    assert sanitize_cell("safe") == "safe"
    assert sanitize_cell(42) == 42
