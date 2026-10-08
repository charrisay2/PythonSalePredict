"""ORM model cho cảnh báo, giải thích của AI và nhật ký thao tác."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)  # stockout | overstock
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)

    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_runs.id"), nullable=True)

    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)  # open | ack

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AIExplanation(Base):
    """Cache giải thích của AI theo prompt_hash để tiết kiệm chi phí."""

    __tablename__ = "ai_explanations"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(64), default="forecast", nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_runs.id"), nullable=True)

    provider: Mapped[str] = mapped_column(String(32), default="fallback", nullable=False)
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
