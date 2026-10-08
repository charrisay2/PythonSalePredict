"""Pydantic schema cho cảnh báo."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_type: str
    severity: str
    product_id: int | None = None
    region_id: int | None = None
    run_id: int | None = None
    risk_score: float
    message: str
    details: dict | None = None
    status: str
    created_at: datetime


class AlertWithNames(AlertOut):
    product_name: str | None = None
    region_name: str | None = None
