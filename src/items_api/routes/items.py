from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from items_api.api.deps import get_item_repo, require_role
from items_api.config import get_settings
from items_api.models.filters import ItemFilters
from items_api.models.item import (
    BulkActionRequest,
    BulkActionResponse,
    ItemCreate,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
    SeedRequest,
    SeedResponse,
)
from items_api.models.user import UserRole
from items_api.repositories.item_repository import ItemRepository
from items_api.services import item_service
from items_api.services.csv_export import generate_csv, parse_id_list
from items_api.services.seed import seed_items

router = APIRouter(prefix="/items", tags=["Items"])


@router.get("/", response_model=ItemListResponse)
async def list_items(
    filters: Annotated[ItemFilters, Depends()],
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.VIEWER))],
    cursor: str | None = Query(None),
    page_size: int = Query(10, ge=1, le=500),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    return await item_service.list_items(
        repo,
        filters,
        cursor=cursor,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/export")
async def export_items(
    filters: Annotated[ItemFilters, Depends()],
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.VIEWER))],
    ids: str | None = Query(None),
    select_all: bool = Query(False),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    id_list = parse_id_list(ids)
    if not select_all and not id_list:
        raise HTTPException(status_code=400, detail="Provide ids or set select_all=true")

    return StreamingResponse(
        generate_csv(
            repo,
            ids=id_list,
            select_all=select_all,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="items-export.csv"'},
    )


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: str,
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.VIEWER))],
):
    return await item_service.get_item(repo, item_id)


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item: ItemCreate,
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.EDITOR))],
):
    return await item_service.create_item(repo, item)


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: str,
    payload: ItemUpdate,
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.EDITOR))],
):
    return await item_service.update_item(repo, item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.EDITOR))],
):
    await item_service.delete_item(repo, item_id)


@router.post("/bulk", response_model=BulkActionResponse)
async def bulk(
    payload: BulkActionRequest,
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.EDITOR))],
):
    return await item_service.bulk_action(repo, payload)


@router.post("/seed", response_model=SeedResponse)
async def seed(
    payload: SeedRequest,
    repo: Annotated[ItemRepository, Depends(get_item_repo)],
    _user: Annotated[dict, Depends(require_role(UserRole.ADMIN))],
):
    settings = get_settings()
    if not settings.allow_seed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seeding is disabled")
    return await seed_items(repo, count=payload.count, clear=payload.clear)
