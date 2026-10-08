"""Pydantic schema cho scenario planning (what-if)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScenarioAssumptions(BaseModel):
    """Các giả định thay đổi so với kịch bản cơ sở."""

    promo_uplift_pct: float = Field(default=0.0, ge=-100, le=300, description="% thay đổi uplift khuyến mãi")
    price_change_pct: float = Field(default=0.0, ge=-90, le=300, description="% thay đổi giá bán")
    demand_shift_pct: float = Field(default=0.0, ge=-90, le=300, description="% dịch chuyển nhu cầu tổng thể")
    lead_time_days: int | None = Field(default=None, ge=0, le=365)
    safety_stock_pct: float = Field(default=0.0, ge=-100, le=500)


class ScenarioCreate(BaseModel):
    base_run_id: int
    name: str = Field(min_length=1, max_length=200)
    assumptions: ScenarioAssumptions = Field(default_factory=ScenarioAssumptions)
    product_ids: list[int] | None = None
    region_ids: list[int] | None = None


class ScenarioResultPoint(BaseModel):
    forecast_date: str
    baseline_yhat: float
    scenario_yhat: float
    delta_pct: float


class InventoryPlan(BaseModel):
    product_id: int | None = None
    region_id: int | None = None
    forecast_units: float = 0.0
    on_hand_qty: float = 0.0
    safety_stock: float = 0.0
    reorder_point: float = 0.0
    suggested_order_qty: float = 0.0
    stockout_risk: float = 0.0
    recommendation: str = ""


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    base_run_id: int
    name: str
    status: str
    assumptions: dict | None = None
    summary: dict | None = None
    error_message: str | None = None
    created_at: datetime
    points: list[ScenarioResultPoint] = Field(default_factory=list)
    inventory_plan: list[InventoryPlan] = Field(default_factory=list)
