from fastapi import FastAPI
from pymongo import AsyncMongoClient

app = FastAPI()

MONGO_URL = "mongodb://root:root@localhost:27017"

client = AsyncMongoClient(MONGO_URL)

db = client["fastapi_db"]
collection = db["items"]

@app.get("/")
def reed_root():
    return {"Hello": "World"}

@app.post("/items")
async def create_item(item: dict):
    result = await collection.insert_one(item)

    return {
        "message": "Item created successfully",
        "item_id": str(result.inserted_id)
    }

@app.get("/items")
async def read_items():
    items = await collection.find().to_list(length=100)

    for item in items:
        item['_id'] = str(item['_id'])

    return {
        "message": "Items retrieved successfully",
        "items": items
    }