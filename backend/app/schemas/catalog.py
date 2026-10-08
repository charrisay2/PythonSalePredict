"""Pydantic schema cho danh mục (sản phẩm, khu vực, kênh, ngày lễ, khuyến mãi)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

DateStr = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------- Region ---------------------------
class RegionBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=32)
    demand_factor: float = 1.0


class RegionCreate(RegionBase):
    pass


class RegionOut(_ORMBase, RegionBase):
    id: int


# --------------------------- Channel ---------------------------
class ChannelBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=32)
    demand_factor: float = 1.0


class ChannelCreate(ChannelBase):
    pass


class ChannelOut(_ORMBase, ChannelBase):
    id: int


# --------------------------- Product ---------------------------
class ProductBase(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = "General"
    unit_price: float = 0.0
    unit_cost: float = 0.0
    lead_time_days: int = Field(default=7, ge=0, le=365)
    is_seasonal: bool = False
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    unit_price: float | None = None
    unit_cost: float | None = None
    lead_time_days: int | None = None
    is_seasonal: bool | None = None
    is_active: bool | None = None


class ProductOut(_ORMBase, ProductBase):
    id: int


# --------------------------- Holiday ---------------------------
class HolidayBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    holiday_date: DateStr
    region_id: int | None = None
    impact_factor: float = 1.0
    is_recurring_yearly: bool = True


class HolidayCreate(HolidayBase):
    pass


class HolidayOut(_ORMBase, HolidayBase):
    id: int


# --------------------------- Promo ---------------------------
class PromoBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    start_date: DateStr
    end_date: DateStr
    discount_pct: float = 0.0
    channel_id: int | None = None
    product_id: int | None = None
    uplift_factor: float = 1.0


class PromoCreate(PromoBase):
    pass


class PromoOut(_ORMBase, PromoBase):
    id: int
