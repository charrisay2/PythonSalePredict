"""ORM model cho dữ liệu bán hàng và tồn kho."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        Index("ix_sales_date_product_region_channel", "sale_date", "product_id", "region_id", "channel_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)  # YYYY-MM-DD
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True, nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True, nullable=False)
    promo_id: Mapped[int | None] = mapped_column(ForeignKey("promos.id"), nullable=True)

    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_holiday: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="sales")  # noqa: F821


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True, nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True, nullable=False)
    on_hand_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    safety_stock: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    incoming_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
