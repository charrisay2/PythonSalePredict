"""Tính toán tồn kho: điểm đặt hàng lại, tồn kho an toàn, rủi ro mất hàng."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.constants import ALERT_OVERSTOCK, ALERT_STOCKOUT
from app.core.utils import safe_round
from app.models import Alert, Forecast, Inventory, Product, Region

DEFAULT_LEAD_TIME = 7
STOCKOUT_ALERT_THRESHOLD = 40.0
OVERSTOCK_ALERT_THRESHOLD = 60.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _demand_by_group(db: Session, run_id: int) -> dict[tuple, dict]:
    buckets: dict[tuple, dict] = defaultdict(
        lambda: {"units": 0.0, "lower": 0.0, "upper": 0.0, "dates": set()}
    )
    for point in db.query(Forecast).filter(Forecast.run_id == run_id).all():
        bucket = buckets[(point.product_id, point.region_id)]
        bucket["units"] += float(point.yhat)
        bucket["lower"] += float(point.yhat_lower)
        bucket["upper"] += float(point.yhat_upper)
        bucket["dates"].add(point.forecast_date)
    return buckets


def compute_inventory_plan(
    db: Session,
    run_id: int,
    lead_time_override: int | None = None,
    safety_stock_pct: float = 0.0,
) -> list[dict]:
    """Trả về kế hoạch tồn kho cho từng nhóm (sản phẩm, khu vực) của một lần dự báo."""
    demand = _demand_by_group(db, run_id)
    if not demand:
        return []

    products = {item.id: item for item in db.query(Product).all()}
    regions = {item.id: item.name for item in db.query(Region).all()}
    inventory_records = db.query(Inventory).all()
    exact = {(item.product_id, item.region_id): item for item in inventory_records}

    def aggregate_inventory(product_id, region_id):
        """Tổng hợp tồn kho khi dự báo không tách theo sản phẩm hoặc khu vực."""
        rows = [
            record
            for record in inventory_records
            if (product_id is None or record.product_id == product_id)
            and (region_id is None or record.region_id == region_id)
        ]
        if not rows:
            return None
        return (
            sum(float(record.on_hand_qty) for record in rows),
            sum(float(record.incoming_qty) for record in rows),
            sum(float(record.safety_stock) for record in rows),
        )

    plan: list[dict] = []
    for (product_id, region_id), bucket in demand.items():
        horizon_days = max(1, len(bucket["dates"]))
        total_units = bucket["units"]
        daily_demand = total_units / horizon_days

        product = products.get(product_id) if product_id else None
        if lead_time_override is not None:
            lead_time = lead_time_override
        elif product is not None:
            lead_time = int(product.lead_time_days or DEFAULT_LEAD_TIME)
        else:
            lead_time = DEFAULT_LEAD_TIME

        record = exact.get((product_id, region_id))
        if record is not None:
            on_hand = float(record.on_hand_qty)
            incoming = float(record.incoming_qty)
            base_safety = float(record.safety_stock)
            has_inventory = True
        else:
            aggregated = aggregate_inventory(product_id, region_id)
            if aggregated is not None:
                on_hand, incoming, base_safety = aggregated
                has_inventory = True
            else:
                on_hand = incoming = base_safety = 0.0
                has_inventory = False

        safety_stock = base_safety * (1.0 + safety_stock_pct / 100.0)
        if not has_inventory:
            # Chưa có dữ liệu tồn kho -> ước lượng tồn kho an toàn = 20% nhu cầu thời gian chờ
            safety_stock = daily_demand * lead_time * 0.2

        lead_time_demand = daily_demand * lead_time
        reorder_point = lead_time_demand + safety_stock
        available = on_hand + incoming
        suggested_order = max(0.0, reorder_point - available)

        if lead_time_demand > 0:
            stockout_risk = _clamp((lead_time_demand - available) / lead_time_demand * 100.0)
        else:
            stockout_risk = 0.0

        overstock_risk = 0.0
        if total_units > 0:
            overstock_risk = _clamp((on_hand - total_units) / total_units * 100.0)

        if stockout_risk >= STOCKOUT_ALERT_THRESHOLD:
            recommendation = (
                f"Rủi ro mất hàng {stockout_risk:.0f}%: nên đặt thêm {suggested_order:.0f} đơn vị "
                f"để về trước điểm đặt hàng lại ({reorder_point:.0f})."
            )
        elif overstock_risk >= OVERSTOCK_ALERT_THRESHOLD:
            recommendation = (
                f"Tồn kho cao hơn nhu cầu dự báo {overstock_risk:.0f}%: cân nhắc chạy khuyến mãi "
                f"hoặc giảm lượng nhập hàng."
            )
        else:
            recommendation = "Mức tồn kho hiện tại nằm trong ngưỡng an toàn so với nhu cầu dự báo."

        plan.append(
            {
                "product_id": product_id,
                "product_name": product.name if product else "Tất cả sản phẩm",
                "region_id": region_id,
                "region_name": regions.get(region_id, "Tất cả khu vực") if region_id else "Tất cả khu vực",
                "horizon_days": horizon_days,
                "forecast_units": safe_round(total_units, 2),
                "daily_demand": safe_round(daily_demand, 2),
                "lead_time_days": lead_time,
                "lead_time_demand": safe_round(lead_time_demand, 2),
                "on_hand_qty": safe_round(on_hand, 2),
                "incoming_qty": safe_round(incoming, 2),
                "safety_stock": safe_round(safety_stock, 2),
                "reorder_point": safe_round(reorder_point, 2),
                "suggested_order_qty": safe_round(suggested_order, 2),
                "stockout_risk": safe_round(stockout_risk, 2),
                "overstock_risk": safe_round(overstock_risk, 2),
                "has_inventory_data": has_inventory,
                "recommendation": recommendation,
            }
        )

    plan.sort(key=lambda item: item["stockout_risk"], reverse=True)
    return plan


def recompute_alerts(db: Session, run_id: int, plan: list[dict] | None = None) -> list[Alert]:
    """Sinh cảnh báo rủi ro mất hàng / tồn kho cao từ kế hoạch tồn kho."""
    if plan is None:
        plan = compute_inventory_plan(db, run_id)

    # Xóa cảnh báo cũ còn "open" của lần dự báo này để tránh trùng lặp
    db.query(Alert).filter(Alert.run_id == run_id, Alert.status == "open").delete()

    alerts: list[Alert] = []
    for item in plan:
        if item["stockout_risk"] >= STOCKOUT_ALERT_THRESHOLD:
            severity = "high" if item["stockout_risk"] >= 70 else "medium"
            alerts.append(
                Alert(
                    alert_type=ALERT_STOCKOUT,
                    severity=severity,
                    product_id=item["product_id"],
                    region_id=item["region_id"],
                    run_id=run_id,
                    risk_score=item["stockout_risk"],
                    message=item["recommendation"],
                    details=item,
                )
            )
        elif item["overstock_risk"] >= OVERSTOCK_ALERT_THRESHOLD:
            alerts.append(
                Alert(
                    alert_type=ALERT_OVERSTOCK,
                    severity="low",
                    product_id=item["product_id"],
                    region_id=item["region_id"],
                    run_id=run_id,
                    risk_score=item["overstock_risk"],
                    message=item["recommendation"],
                    details=item,
                )
            )

    if alerts:
        db.bulk_save_objects(alerts)
        db.commit()

    # Đọc lại từ CSDL để có đầy đủ id / created_at / status
    return (
        db.query(Alert)
        .filter(Alert.run_id == run_id)
        .order_by(Alert.risk_score.desc())
        .all()
    )
