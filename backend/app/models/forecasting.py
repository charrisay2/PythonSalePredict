"""ORM model cho kết quả dự báo và kịch bản (scenario planning)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import JOB_PENDING
from app.db.base import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ForecastRun(Base):
    """Một lần huấn luyện + dự báo (có thể gồm nhiều mô hình để so sánh)."""

    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="Forecast run", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default=JOB_PENDING, nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    granularity: Mapped[str] = mapped_column(String(32), default="total", nullable=False)

    # Bộ lọc phạm vi dự báo: {"product_ids": [...], "region_ids": [...], "channel_ids": [...]}
    scope: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # Kết quả backtest của mô hình được chọn: {"mape":..., "rmse":..., ...}
    metrics: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # Bảng xếp hạng tất cả mô hình đã huấn luyện: [{model, mape, rmse, ...}, ...]
    leaderboard: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    # Phân rã thành phần đóng góp: {"trend":..., "weekly":..., "holiday":..., "promo":...}
    drivers: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    train_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    train_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (Index("ix_forecasts_run_date", "run_id", "forecast_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"), index=True, nullable=False)

    forecast_date: Mapped[str] = mapped_column(String(10), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)

    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    yhat: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    yhat_lower: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    yhat_upper: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class Scenario(Base):
    """Kịch bản what-if dựa trên một forecast run."""

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="Scenario", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=JOB_PENDING, nullable=False)

    # Giả định: {"promo_uplift_pct": 15, "price_change_pct": -5, "lead_time_days": 10, "safety_stock_pct": 20}
    assumptions: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # Tóm tắt kết quả: {"baseline_total":..., "scenario_total":..., "delta_pct":...}
    summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScenarioResult(Base):
    __tablename__ = "scenario_results"
    __table_args__ = (Index("ix_scenario_results_scenario_date", "scenario_id", "forecast_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), index=True, nullable=False)

    forecast_date: Mapped[str] = mapped_column(String(10), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)

    baseline_yhat: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    scenario_yhat: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    delta_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
