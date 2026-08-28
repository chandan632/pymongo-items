from fastapi import APIRouter, HTTPException, status

from pymongo_tutorial.models.item import ItemCreate, ItemResponse
from pymongo_tutorial.services.item_service import (
    create_item,
    get_items,
    get_item_by_id,
)

router = APIRouter(
    prefix="/items",
    tags=["Items"]
)


@router.post(
    "/",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED
)
async def create(item: ItemCreate):
    return await create_item(item)


@router.get(
    "/",
    response_model=list[ItemResponse]
)
async def get_all():
    return await get_items()


@router.get(
    "/{item_id}",
    response_model=ItemResponse
)
async def get_one(item_id: str):
    item = await get_item_by_id(item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )

    return item