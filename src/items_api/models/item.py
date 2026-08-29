from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class ItemStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    DRAFT = "draft"


class ItemCategory(StrEnum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    FOOD = "food"
    HOME = "home"
    SPORTS = "sports"
    BOOKS = "books"
    OTHER = "other"


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    sku: str = Field(..., min_length=1, max_length=64)
    category: ItemCategory
    status: ItemStatus = ItemStatus.ACTIVE
    price: float = Field(..., ge=0)
    quantity: int = Field(..., ge=0)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    category: ItemCategory | None = None
    status: ItemStatus | None = None
    price: float | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ItemResponse(BaseModel):
    id: str
    name: str
    sku: str
    category: ItemCategory
    status: ItemStatus
    price: float
    quantity: int
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ItemListResponse(BaseModel):
    data: list[ItemResponse]
    meta: PaginationMeta


class BulkAction(StrEnum):
    DELETE = "delete"
    SET_STATUS = "set_status"
    ADJUST_QUANTITY = "adjust_quantity"


class BulkActionRequest(BaseModel):
    action: BulkAction
    ids: list[str] | None = Field(default=None, max_length=1000)
    exclude_ids: list[str] | None = Field(default=None, max_length=1000)
    select_all: bool = False
    q: str | None = Field(default=None, max_length=200)
    category: ItemCategory | None = None
    status: ItemStatus | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    min_quantity: int | None = Field(default=None, ge=0)
    max_quantity: int | None = Field(default=None, ge=0)
    status_value: ItemStatus | None = None
    quantity_delta: int | None = None

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) == 0:
            raise ValueError("ids must not be empty when provided")
        return value

    @field_validator("exclude_ids")
    @classmethod
    def validate_exclude_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) == 0:
            raise ValueError("exclude_ids must not be empty when provided")
        return value


class BulkActionResponse(BaseModel):
    matched: int
    modified: int
    action: BulkAction


class SeedRequest(BaseModel):
    count: int = Field(default=5000, ge=1, le=50000)
    clear: bool = False


class SeedResponse(BaseModel):
    inserted: int
    total: int
