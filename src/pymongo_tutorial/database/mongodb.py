from pymongo import AsyncMongoClient

from pymongo_tutorial.config import settings

client = AsyncMongoClient(settings.mongo_uri)
db = client[settings.mongo_db_name]

items_collection = db["items"]