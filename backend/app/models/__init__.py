"""Gọi tất cả ORM model để `Base.metadata` nhìn thấy đầy đủ."""

from app.db.base import Base
from app.models.catalog import Channel, Holiday, Product, Promo, Region
from app.models.forecasting import Forecast, ForecastRun, Scenario, ScenarioResult
from app.models.ops import AIExplanation, Alert, AuditLog
from app.models.sales import Inventory, Sale
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Region",
    "Channel",
    "Product",
    "Holiday",
    "Promo",
    "Sale",
    "Inventory",
    "ForecastRun",
    "Forecast",
    "Scenario",
    "ScenarioResult",
    "Alert",
    "AIExplanation",
    "AuditLog",
]
