"""Pydantic schema cho dữ liệu bán hàng, upload và tồn kho."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_date: str
    product_id: int
    region_id: int
    channel_id: int
    promo_id: int | None = None
    quantity: float
    unit_price: float
    revenue: float
    discount_pct: float
    is_holiday: int


class SalesFilter(BaseModel):
    product_ids: list[int] | None = None
    region_ids: list[int] | None = None
    channel_ids: list[int] | None = None
    start_date: str | None = None
    end_date: str | None = None


class UploadResult(BaseModel):
    rows_received: int = 0
    rows_inserted: int = 0
    rows_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    date_start: str | None = None
    date_end: str | None = None


class GenerateSampleRequest(BaseModel):
    days: int = Field(default=540, ge=60, le=1825)
    products: int = Field(default=12, ge=1, le=100)
    regions: int = Field(default=4, ge=1, le=20)
    channels: int = Field(default=3, ge=1, le=10)
    seed: int = 42
    reset: bool = True


class InventoryBase(BaseModel):
    product_id: int
    region_id: int
    on_hand_qty: float = 0.0
    safety_stock: float = 0.0
    incoming_qty: float = 0.0


class InventoryUpsert(InventoryBase):
    pass


class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    region_id: int
    on_hand_qty: float
    safety_stock: float
    incoming_qty: float
    updated_at: datetime


class SalesStats(BaseModel):
    total_rows: int
    total_units: float
    total_revenue: float
    date_start: str | None = None
    date_end: str | None = None
    products: int = 0
    regions: int = 0
    channels: int = 0
