"""Pydantic schema cho dashboard tổng quan."""

from pydantic import BaseModel, Field


class KpiCard(BaseModel):
    key: str
    label: str
    value: float
    unit: str = ""
    delta_pct: float | None = None
    hint: str = ""


class DashboardSummary(BaseModel):
    total_revenue: float = 0.0
    total_units: float = 0.0
    active_products: int = 0
    date_start: str | None = None
    date_end: str | None = None
    latest_run_id: int | None = None
    forecast_accuracy: float | None = None
    forecast_units: float | None = None
    open_alerts: int = 0
    kpis: list[KpiCard] = Field(default_factory=list)
    top_products: list[dict] = Field(default_factory=list)
    recent_runs: list[dict] = Field(default_factory=list)
    monthly_series: list[dict] = Field(default_factory=list)
