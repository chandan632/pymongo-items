from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from pymongo.errors import BulkWriteError

from items_api.models.item import ItemCategory, ItemStatus, SeedResponse
from items_api.repositories.item_repository import ItemRepository

ADJECTIVES = [
    "Compact",
    "Durable",
    "Classic",
    "Modern",
    "Portable",
    "Premium",
    "Standard",
    "Lightweight",
    "Heavy-duty",
    "Eco",
]
NOUNS = [
    "Lamp",
    "Chair",
    "Monitor",
    "Bottle",
    "Jacket",
    "Keyboard",
    "Backpack",
    "Speaker",
    "Notebook",
    "Helmet",
    "Mixer",
    "Toaster",
    "Drill",
    "Camera",
    "Router",
]
DESCRIPTIONS = [
    "Reliable everyday use product.",
    "Popular with regular customers.",
    "Suitable for home and office.",
    "Built for long-term use.",
    "Good balance of price and quality.",
    None,
    None,
]


def build_item_doc(index: int) -> dict:
    now = datetime.now(UTC)
    created = now - timedelta(days=random.randint(0, 730), hours=random.randint(0, 23))
    return {
        "name": f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)} {index}",
        "sku": f"SKU-{index:06d}",
        "category": random.choice(list(ItemCategory)).value,
        "status": random.choice(list(ItemStatus)).value,
        "price": round(random.uniform(2.5, 999.99), 2),
        "quantity": random.randint(0, 500),
        "description": random.choice(DESCRIPTIONS),
        "created_at": created,
        "updated_at": created + timedelta(days=random.randint(0, 30)),
    }


async def seed_items(
    repo: ItemRepository,
    *,
    count: int,
    clear: bool,
) -> SeedResponse:
    if clear:
        await repo.delete_many({})

    start_index = await repo.max_sku_index()
    inserted = 0
    remaining = count
    batch_size = 1000

    while remaining > 0:
        batch = min(batch_size, remaining)
        docs = [build_item_doc(start_index + inserted + i + 1) for i in range(batch)]
        try:
            inserted += await repo.insert_many(docs)
        except BulkWriteError as exc:
            inserted += int(exc.details.get("nInserted", 0))
            break
        remaining -= batch

    total = await repo.count({})
    return SeedResponse(inserted=inserted, total=total)
