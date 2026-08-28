from fastapi import FastAPI

from pymongo_tutorial.routes.item import router as item_router

app = FastAPI()

app.include_router(item_router)


@app.get("/")
async def root():
    return {
        "message": "FastAPI + MongoDB is working"
    }