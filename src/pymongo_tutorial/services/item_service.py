from pymongo_tutorial.database.mongodb import items_collection
from pymongo_tutorial.models.item import ItemCreate


async def create_item(item: ItemCreate):
    item_data = item.model_dump()

    result = await items_collection.insert_one(item_data)

    return {
        "id": str(result.inserted_id),
        **item_data
    }


async def get_items():
    items = await items_collection.find().to_list(length=100)

    return [
        {
            "id": str(item["_id"]),
            "name": item["name"],
            "price": item["price"],
            "description": item.get("description"),
        }
        for item in items
    ]


async def get_item_by_id(item_id):
    from bson import ObjectId

    item = await items_collection.find_one({
        "_id": ObjectId(item_id)
    })

    if not item:
        return None

    return {
        "id": str(item["_id"]),
        "name": item["name"],
        "price": item["price"],
        "description": item.get("description"),
    }