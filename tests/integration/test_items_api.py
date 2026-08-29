from __future__ import annotations

import csv
import io

import pytest

from tests.conftest import auth_headers, unwrap


def sample_item(**overrides):
    payload = {
        "name": "Test Lamp",
        "sku": "SKU-TEST-001",
        "category": "electronics",
        "status": "active",
        "price": 49.99,
        "quantity": 10,
        "description": "Test item",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_crud_with_auth(client, editor_user, viewer_user):
    headers = auth_headers(editor_user)
    created = await client.post("/api/v1/items/", json=sample_item(), headers=headers)
    assert created.status_code == 201
    body = unwrap(created)
    item_id = body["id"]

    fetched = await client.get(
        f"/api/v1/items/{item_id}",
        headers=auth_headers(viewer_user),
    )
    assert fetched.status_code == 200
    assert unwrap(fetched)["name"] == "Test Lamp"

    updated = await client.patch(
        f"/api/v1/items/{item_id}",
        json={"name": "Updated Lamp", "price": 59.5},
        headers={**headers, "Idempotency-Key": "update-1"},
    )
    assert updated.status_code == 200
    updated_data = unwrap(updated)
    assert updated_data["name"] == "Updated Lamp"
    assert updated_data["price"] == 59.5

    deleted = await client.delete(
        f"/api/v1/items/{item_id}",
        headers={**headers, "Idempotency-Key": "delete-1"},
    )
    assert deleted.status_code == 204
    missing = await client.get(f"/api/v1/items/{item_id}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_list_filter_sort_paginate(client, editor_user):
    headers = auth_headers(editor_user)
    for i in range(5):
        await client.post(
            "/api/v1/items/",
            json=sample_item(sku=f"SKU-LIST-{i}", name=f"Lamp {i}", price=10 + i),
            headers=headers,
        )

    response = await client.get(
        "/api/v1/items/",
        params={
            "q": "Lamp",
            "status": "active",
            "sort_by": "price",
            "sort_order": "asc",
            "page": 1,
            "page_size": 2,
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    items = body["data"]
    meta = body["meta"]
    assert meta["total"] == 5
    assert len(items) == 2
    assert items[0]["price"] <= items[1]["price"]


@pytest.mark.asyncio
async def test_duplicate_sku_conflict(client, editor_user):
    headers = auth_headers(editor_user)
    await client.post("/api/v1/items/", json=sample_item(), headers=headers)
    again = await client.post(
        "/api/v1/items/",
        json=sample_item(name="Other"),
        headers=headers,
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_invalid_object_id(client, editor_user):
    response = await client.get(
        "/api/v1/items/not-an-object-id",
        headers=auth_headers(editor_user),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_empty_patch(client, editor_user):
    headers = auth_headers(editor_user)
    created = unwrap(await client.post("/api/v1/items/", json=sample_item(), headers=headers))
    response = await client.patch(
        f"/api/v1/items/{created['id']}",
        json={},
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_invalid_sort_by(client, editor_user):
    response = await client.get(
        "/api/v1/items/",
        params={"sort_by": "not_a_field"},
        headers=auth_headers(editor_user),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_bulk_set_status_with_ids(client, editor_user):
    headers = auth_headers(editor_user)
    ids = []
    for i in range(3):
        body = unwrap(
            await client.post(
                "/api/v1/items/",
                json=sample_item(sku=f"SKU-BULK-{i}"),
                headers=headers,
            )
        )
        ids.append(body["id"])

    result = await client.post(
        "/api/v1/items/bulk",
        json={"action": "set_status", "ids": ids, "status_value": "archived"},
        headers={**headers, "Idempotency-Key": "bulk-1"},
    )
    assert result.status_code == 200
    assert unwrap(result)["modified"] == 3


@pytest.mark.asyncio
async def test_bulk_select_all_with_category_filter(client, editor_user):
    headers = auth_headers(editor_user)
    await client.post(
        "/api/v1/items/",
        json=sample_item(sku="SKU-ELEC-1", category="electronics"),
        headers=headers,
    )
    await client.post(
        "/api/v1/items/",
        json=sample_item(sku="SKU-FOOD-1", category="food"),
        headers=headers,
    )

    result = await client.post(
        "/api/v1/items/bulk",
        json={
            "action": "set_status",
            "select_all": True,
            "category": "electronics",
            "status_value": "inactive",
        },
        headers={**headers, "Idempotency-Key": "bulk-cat"},
    )
    assert result.status_code == 200
    assert unwrap(result)["modified"] == 1

    listed = await client.get(
        "/api/v1/items/",
        params={"category": "electronics"},
        headers=headers,
    )
    body = listed.json()
    assert body["success"] is True
    assert body["data"][0]["status"] == "inactive"


@pytest.mark.asyncio
async def test_bulk_delete_select_all_empty_filter(client, editor_user):
    headers = auth_headers(editor_user)
    result = await client.post(
        "/api/v1/items/bulk",
        json={"action": "delete", "select_all": True},
        headers={**headers, "Idempotency-Key": "bulk-del-empty"},
    )
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_bulk_with_exclude_ids(client, editor_user):
    headers = auth_headers(editor_user)
    ids = []
    for i in range(3):
        body = unwrap(
            await client.post(
                "/api/v1/items/",
                json=sample_item(sku=f"SKU-EX-{i}", category="home"),
                headers=headers,
            )
        )
        ids.append(body["id"])

    result = await client.post(
        "/api/v1/items/bulk",
        json={
            "action": "set_status",
            "select_all": True,
            "category": "home",
            "exclude_ids": [ids[0]],
            "status_value": "archived",
        },
        headers={**headers, "Idempotency-Key": "bulk-ex"},
    )
    assert result.status_code == 200
    assert unwrap(result)["modified"] == 2

    kept = await client.get(f"/api/v1/items/{ids[0]}", headers=headers)
    assert unwrap(kept)["status"] == "active"


@pytest.mark.asyncio
async def test_adjust_quantity_clamps_at_zero(client, editor_user):
    headers = auth_headers(editor_user)
    created = unwrap(
        await client.post(
            "/api/v1/items/",
            json=sample_item(quantity=5, sku="SKU-QTY-1"),
            headers=headers,
        )
    )

    result = await client.post(
        "/api/v1/items/bulk",
        json={
            "action": "adjust_quantity",
            "ids": [created["id"]],
            "quantity_delta": -100,
        },
        headers={**headers, "Idempotency-Key": "bulk-qty"},
    )
    assert result.status_code == 200

    fetched = await client.get(f"/api/v1/items/{created['id']}", headers=headers)
    assert unwrap(fetched)["quantity"] == 0


@pytest.mark.asyncio
async def test_export_csv_structure_and_formula_escape(client, editor_user):
    headers = auth_headers(editor_user)
    await client.post(
        "/api/v1/items/",
        json=sample_item(name="=1+1", description="+CMD"),
        headers=headers,
    )

    response = await client.get(
        "/api/v1/items/export",
        params={"select_all": True},
        headers=headers,
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    assert len(rows) == 1
    assert "id" in reader.fieldnames
    assert "sku" in reader.fieldnames
    assert rows[0]["name"].startswith("'")
    assert rows[0]["description"].startswith("'")
    assert "SKU-TEST-001" in response.text


@pytest.mark.asyncio
async def test_idempotency_replay_header(client, editor_user):
    headers = {
        **auth_headers(editor_user),
        "Idempotency-Key": "create-once",
    }
    first = await client.post("/api/v1/items/", json=sample_item(), headers=headers)
    second = await client.post("/api/v1/items/", json=sample_item(), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.headers.get("x-idempotent-replay") == "true"
    assert unwrap(first)["id"] == unwrap(second)["id"]


@pytest.mark.asyncio
async def test_seed_works_and_max_sku_after_partial_delete(client, admin_user, editor_user):
    admin_headers = auth_headers(admin_user)
    editor_headers = auth_headers(editor_user)

    seeded = await client.post(
        "/api/v1/items/seed",
        json={"count": 5, "clear": True},
        headers=admin_headers,
    )
    assert seeded.status_code == 200
    seeded_data = unwrap(seeded)
    assert seeded_data["inserted"] == 5
    assert seeded_data["total"] == 5

    listed = await client.get(
        "/api/v1/items/",
        params={"page_size": 50, "sort_by": "sku", "sort_order": "asc"},
        headers=editor_headers,
    )
    body = listed.json()
    assert body["success"] is True
    items = body["data"]
    assert len(items) == 5
    for item in items[1:4]:
        await client.delete(
            f"/api/v1/items/{item['id']}",
            headers=editor_headers,
        )

    again = await client.post(
        "/api/v1/items/seed",
        json={"count": 2, "clear": False},
        headers=admin_headers,
    )
    assert again.status_code == 200
    assert unwrap(again)["inserted"] == 2

    listed2 = await client.get(
        "/api/v1/items/",
        params={"page_size": 50, "sort_by": "sku", "sort_order": "asc"},
        headers=editor_headers,
    )
    body2 = listed2.json()
    skus = sorted(row["sku"] for row in body2["data"])
    assert "SKU-000006" in skus
    assert "SKU-000007" in skus
