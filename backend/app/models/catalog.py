"""ORM model cho danh mục: sản phẩm, khu vực, kênh bán."""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # Hệ số nhu cầu tương đối theo vùng (dùng cho sinh dữ liệu / giải thích)
    demand_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    demand_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="General", nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    is_seasonal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sales: Mapped[list["Sale"]] = relationship(back_populates="product")  # noqa: F821


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    holiday_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)  # YYYY-MM-DD
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    # Hệ số tác động lên nhu cầu (1.0 = không đổi, 1.3 = tăng 30%)
    impact_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_recurring_yearly: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Promo(Base):
    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    start_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    end_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    # Hệ số nhu cầu khi khuyến mãi đang chạy
    uplift_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
