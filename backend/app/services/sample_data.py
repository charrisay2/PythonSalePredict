"""Sinh dữ liệu bán hàng mẫu (có mùa vụ, ngày lễ, khuyến mãi, khu vực, kênh bán)."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

import numpy as np
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.core.utils import safe_round
from app.models import (
    AIExplanation,
    Alert,
    Channel,
    Forecast,
    ForecastRun,
    Holiday,
    Inventory,
    Product,
    Promo,
    Region,
    Sale,
    Scenario,
    ScenarioResult,
)

REGION_SEED = [
    ("Miền Bắc", "MB", 1.25),
    ("Miền Trung", "MT", 0.85),
    ("Miền Nam", "MN", 1.45),
    ("Miền Tây", "MTY", 0.70),
]

CHANNEL_SEED = [
    ("Cửa hàng bán lẻ", "OFF", 1.00),
    ("Thương mại điện tử", "ONL", 1.30),
    ("Đại lý bán buôn", "WSL", 0.80),
]

PRODUCT_SEED = [
    ("SP001", "Trà xanh đóng chai", "Đồ uống", 12000, 8000, 5, True, 55),
    ("SP002", "Cà phê rang xay", "Đồ uống", 85000, 55000, 7, False, 18),
    ("SP003", "Nước suối tinh khiết", "Đồ uống", 6000, 3500, 4, True, 90),
    ("SP004", "Bánh quy bơ", "Bánh kẹo", 45000, 28000, 10, True, 24),
    ("SP005", "Kẹo dẻo trái cây", "Bánh kẹo", 25000, 15000, 10, False, 32),
    ("SP006", "Socola đen", "Bánh kẹo", 65000, 42000, 12, True, 20),
    ("SP007", "Nước giặt 3kg", "Gia dụng", 145000, 105000, 14, False, 12),
    ("SP008", "Nước rửa chén 1L", "Gia dụng", 42000, 28000, 14, False, 22),
    ("SP009", "Dầu gội thảo dược", "Chăm sóc cá nhân", 95000, 62000, 10, False, 15),
    ("SP010", "Mì gói tôm chua cay", "Thực phẩm", 8000, 5000, 6, True, 120),
]

HOLIDAY_SEED = [
    ("Tết Nguyên Đán", "2025-01-29", 1.65),
    ("Quốc tế Lao động", "2025-05-01", 1.30),
    ("Quốc khánh", "2025-09-02", 1.35),
    ("Trung thu", "2025-10-06", 1.25),
    ("Black Friday", "2025-11-28", 1.55),
    ("Giáng sinh", "2025-12-24", 1.45),
    ("Tết Dương lịch", "2025-12-31", 1.40),
]

PROMO_SEED = [
    ("Khuyến mãi hè", "06-01", "06-20", 15.0, 1.25),
    ("Sale giữa năm", "07-10", "07-20", 20.0, 1.35),
    ("Back to school", "08-15", "08-31", 12.0, 1.20),
    ("Mua sắm cuối năm", "11-20", "11-30", 25.0, 1.50),
    ("Giáng sinh an lành", "12-15", "12-25", 18.0, 1.40),
    ("Tết sum vầy", "01-15", "01-28", 22.0, 1.45),
    ("Kích cầu mùa 3", "03-01", "03-15", 10.0, 1.15),
    ("Sale cuối tuần vàng", "09-20", "09-30", 14.0, 1.22),
]


def _clear_data(db: Session) -> None:
    for model in (
        Alert,
        AIExplanation,
        ScenarioResult,
        Scenario,
        Forecast,
        ForecastRun,
        Inventory,
        Sale,
        Promo,
        Holiday,
        Product,
        Channel,
        Region,
    ):
        db.execute(delete(model))
    db.commit()


def generate_sample_data(
    db: Session,
    days: int = 540,
    products: int = 10,
    regions: int = 4,
    channels: int = 3,
    seed: int = 42,
    reset: bool = True,
) -> dict:
    """Tạo danh mục + dữ liệu bán hàng theo ngày. Trả về thống kê đã tạo."""
    rng = np.random.default_rng(seed)
    random.seed(seed)

    if reset:
        _clear_data(db)

    # --- Danh mục ---
    region_rows = [
        Region(name=name, code=code, demand_factor=factor)
        for name, code, factor in REGION_SEED[: max(1, min(regions, len(REGION_SEED)))]
    ]
    channel_rows = [
        Channel(name=name, code=code, demand_factor=factor)
        for name, code, factor in CHANNEL_SEED[: max(1, min(channels, len(CHANNEL_SEED)))]
    ]
    product_rows = [
        Product(
            sku=sku,
            name=name,
            category=category,
            unit_price=price,
            unit_cost=cost,
            lead_time_days=lead_time,
            is_seasonal=seasonal,
            is_active=True,
        )
        for sku, name, category, price, cost, lead_time, seasonal, _base in PRODUCT_SEED[
            : max(1, min(products, len(PRODUCT_SEED)))
        ]
    ]
    db.add_all(region_rows + channel_rows + product_rows)
    db.commit()
    for row in region_rows + channel_rows + product_rows:
        db.refresh(row)

    holiday_rows = [
        Holiday(
            name=name,
            holiday_date=holiday_date,
            region_id=None,
            impact_factor=factor,
            is_recurring_yearly=True,
        )
        for name, holiday_date, factor in HOLIDAY_SEED
    ]

    current_year = date.today().year
    promo_rows = []
    for name, start_md, end_md, discount, uplift in PROMO_SEED:
        for year in (current_year - 1, current_year, current_year + 1):
            promo_rows.append(
                Promo(
                    name=f"{name} {year}",
                    start_date=f"{year}-{start_md}",
                    end_date=f"{year}-{end_md}",
                    discount_pct=discount,
                    uplift_factor=uplift,
                    channel_id=None,
                    product_id=None,
                )
            )
    db.add_all(holiday_rows + promo_rows)
    db.commit()

    # --- Bảng tra cứu nhanh ---
    holiday_map: dict[str, float] = {}
    for row in holiday_rows:
        holiday_map[row.holiday_date[5:]] = max(holiday_map.get(row.holiday_date[5:], 1.0), row.impact_factor)

    promo_windows = [
        (row.start_date, row.end_date, row.uplift_factor, row.discount_pct) for row in promo_rows
    ]

    base_demand = {
        row.sku: PRODUCT_SEED[index][7]
        for index, row in enumerate(product_rows)
    }

    today = date.today()
    start_day = today - timedelta(days=days - 1)

    records: list[dict] = []
    daily_totals: dict[str, float] = {}

    for offset in range(days):
        current = start_day + timedelta(days=offset)
        date_str = current.isoformat()
        dow = current.weekday()
        weekend_factor = 1.18 if dow >= 5 else 1.0
        yearly_factor = 1.0 + 0.22 * math.sin(2 * math.pi * (current.timetuple().tm_yday - 300) / 365.25)
        trend_factor = 1.0 + 0.0004 * offset
        holiday_factor = holiday_map.get(date_str[5:], 1.0)

        active_promo = None
        for start_date, end_date, uplift, discount in promo_windows:
            if start_date <= date_str <= end_date:
                if active_promo is None or uplift > active_promo[0]:
                    active_promo = (uplift, discount)
        promo_factor = active_promo[0] if active_promo else 1.0
        promo_discount = active_promo[1] if active_promo else 0.0

        for product in product_rows:
            base = base_demand.get(product.sku, 20)
            product_seasonal = 1.15 if product.is_seasonal else 1.0
            for region in region_rows:
                for channel in channel_rows:
                    mean = (
                        base
                        * region.demand_factor
                        * channel.demand_factor
                        * weekend_factor
                        * yearly_factor
                        * trend_factor
                        * holiday_factor
                        * promo_factor
                        * product_seasonal
                    )
                    noise = float(rng.normal(1.0, 0.13))
                    quantity = max(0.0, mean * noise)
                    quantity = round(quantity, 2)
                    if quantity <= 0:
                        continue

                    unit_price = product.unit_price * (1.0 - promo_discount / 100.0)
                    records.append(
                        {
                            "sale_date": date_str,
                            "product_id": product.id,
                            "region_id": region.id,
                            "channel_id": channel.id,
                            "promo_id": None,
                            "quantity": quantity,
                            "unit_price": safe_round(unit_price, 2),
                            "revenue": safe_round(unit_price * quantity, 2),
                            "discount_pct": promo_discount,
                            "is_holiday": 1 if holiday_factor > 1.001 else 0,
                        }
                    )
                    daily_totals[date_str] = daily_totals.get(date_str, 0.0) + quantity

    # Chèn theo lô để đảm bảo tốc độ
    batch_size = 5000
    for index in range(0, len(records), batch_size):
        db.execute(insert(Sale), records[index : index + batch_size])
    db.commit()

    # --- Tồn kho: cố tình tạo cả trường hợp rủi ro mất hàng ---
    inventory_rows = []
    for product in product_rows:
        recent_daily = base_demand.get(product.sku, 20) * 0.85
        for region in region_rows:
            expected_daily = recent_daily * region.demand_factor
            coverage_days = float(rng.uniform(3.0, 32.0))
            on_hand = max(0.0, expected_daily * coverage_days)
            inventory_rows.append(
                Inventory(
                    product_id=product.id,
                    region_id=region.id,
                    on_hand_qty=safe_round(on_hand, 2),
                    safety_stock=safe_round(expected_daily * 3.0, 2),
                    incoming_qty=safe_round(expected_daily * float(rng.uniform(0.0, 4.0)), 2),
                )
            )
    db.add_all(inventory_rows)
    db.commit()

    total_units = sum(daily_totals.values())
    return {
        "products": len(product_rows),
        "regions": len(region_rows),
        "channels": len(channel_rows),
        "holidays": len(holiday_rows),
        "promos": len(promo_rows),
        "sales_rows": len(records),
        "days": days,
        "date_start": start_day.isoformat(),
        "date_end": today.isoformat(),
        "total_units": safe_round(total_units, 2),
    }
