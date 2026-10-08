"""Scenario planning: chạy kịch bản what-if trên một lần dự báo cơ sở."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import JOB_COMPLETED, JOB_FAILED, JOB_RUNNING
from app.core.utils import safe_round
from app.models import Forecast, ForecastRun, Scenario, ScenarioResult
from app.services.inventory import compute_inventory_plan

# Độ co giãn của nhu cầu theo giá (giá tăng 1% -> nhu cầu giảm ~1.1%)
PRICE_ELASTICITY = -1.1


def _demand_factor(assumptions: dict) -> float:
    factor = 1.0 + float(assumptions.get("demand_shift_pct", 0.0)) / 100.0
    promo_pct = float(assumptions.get("promo_uplift_pct", 0.0))
    if promo_pct:
        factor *= 1.0 + promo_pct / 100.0
    price_pct = float(assumptions.get("price_change_pct", 0.0))
    if price_pct:
        factor *= (1.0 + price_pct / 100.0) ** PRICE_ELASTICITY
    return max(0.0, factor)


def _rescale_plan(base_plan: list[dict], factor: float, assumptions: dict) -> list[dict]:
    """Áp lại hệ số nhu cầu lên kế hoạch tồn kho của kịch bản cơ sở."""
    lead_override = assumptions.get("lead_time_days")
    safety_pct = float(assumptions.get("safety_stock_pct", 0.0))
    plan: list[dict] = []

    for item in base_plan:
        horizon_days = max(1, int(item.get("horizon_days", 1)))
        forecast_units = float(item.get("forecast_units", 0.0)) * factor
        daily_demand = forecast_units / horizon_days
        lead_time = int(lead_override) if lead_override is not None else int(item.get("lead_time_days", 7))

        on_hand = float(item.get("on_hand_qty", 0.0))
        incoming = float(item.get("incoming_qty", 0.0))
        safety_stock = float(item.get("safety_stock", 0.0)) * (1.0 + safety_pct / 100.0)
        lead_time_demand = daily_demand * lead_time
        reorder_point = lead_time_demand + safety_stock
        available = on_hand + incoming
        suggested_order = max(0.0, reorder_point - available)
        stockout_risk = (
            max(0.0, min(100.0, (lead_time_demand - available) / lead_time_demand * 100.0))
            if lead_time_demand > 0
            else 0.0
        )

        if stockout_risk >= 40:
            recommendation = (
                f"Kịch bản làm rủi ro mất hàng lên {stockout_risk:.0f}%: cần đặt thêm "
                f"{suggested_order:.0f} đơn vị."
            )
        else:
            recommendation = "Kịch bản này vẫn giữ được mức tồn kho an toàn."

        plan.append(
            {
                **item,
                "horizon_days": horizon_days,
                "forecast_units": safe_round(forecast_units, 2),
                "daily_demand": safe_round(daily_demand, 2),
                "lead_time_days": lead_time,
                "safety_stock": safe_round(safety_stock, 2),
                "reorder_point": safe_round(reorder_point, 2),
                "suggested_order_qty": safe_round(suggested_order, 2),
                "stockout_risk": safe_round(stockout_risk, 2),
                "recommendation": recommendation,
            }
        )

    plan.sort(key=lambda entry: entry["stockout_risk"], reverse=True)
    return plan


def create_scenario(db: Session, request, user_id: int | None = None) -> Scenario:
    base_run = db.get(ForecastRun, request.base_run_id)
    if base_run is None:
        raise ValueError("Không tìm thấy lần dự báo cơ sở (base_run_id)")

    assumptions = request.assumptions.model_dump()
    scenario = Scenario(
        base_run_id=base_run.id,
        name=request.name,
        created_by=user_id,
        status=JOB_RUNNING,
        assumptions=assumptions,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    try:
        query = db.query(Forecast).filter(Forecast.run_id == base_run.id)
        if request.product_ids:
            query = query.filter(Forecast.product_id.in_(request.product_ids))
        if request.region_ids:
            query = query.filter(Forecast.region_id.in_(request.region_ids))
        points = query.all()
        if not points:
            raise ValueError("Lần dự báo cơ sở chưa có điểm dự báo nào")

        factor = _demand_factor(assumptions)

        rows: list[ScenarioResult] = []
        by_date: dict[str, dict] = defaultdict(lambda: {"baseline": 0.0, "scenario": 0.0})
        baseline_total = 0.0
        scenario_total = 0.0

        for point in points:
            baseline = float(point.yhat)
            scenario_value = baseline * factor
            delta_pct = ((scenario_value - baseline) / baseline * 100.0) if baseline else 0.0
            rows.append(
                ScenarioResult(
                    scenario_id=scenario.id,
                    forecast_date=point.forecast_date,
                    product_id=point.product_id,
                    region_id=point.region_id,
                    baseline_yhat=safe_round(baseline, 3),
                    scenario_yhat=safe_round(scenario_value, 3),
                    delta_pct=safe_round(delta_pct, 2),
                )
            )
            baseline_total += baseline
            scenario_total += scenario_value
            bucket = by_date[point.forecast_date]
            bucket["baseline"] += baseline
            bucket["scenario"] += scenario_value

        db.bulk_save_objects(rows)

        base_plan = compute_inventory_plan(
            db,
            base_run.id,
            lead_time_override=assumptions.get("lead_time_days"),
            safety_stock_pct=float(assumptions.get("safety_stock_pct", 0.0)),
        )
        inventory_plan = _rescale_plan(base_plan, factor, assumptions)

        peak_date = max(by_date.items(), key=lambda kv: kv[1]["scenario"])[0] if by_date else None
        days = max(1, len(by_date))
        delta_total_pct = ((scenario_total - baseline_total) / baseline_total * 100.0) if baseline_total else 0.0

        scenario.summary = {
            "baseline_total_units": safe_round(baseline_total, 2),
            "scenario_total_units": safe_round(scenario_total, 2),
            "delta_units": safe_round(scenario_total - baseline_total, 2),
            "delta_pct": safe_round(delta_total_pct, 2),
            "baseline_daily_avg": safe_round(baseline_total / days, 2),
            "scenario_daily_avg": safe_round(scenario_total / days, 2),
            "peak_date": peak_date,
            "horizon_days": days,
            "demand_factor": safe_round(factor, 4),
            "price_elasticity_used": PRICE_ELASTICITY,
            "assumptions": assumptions,
            "inventory_plan": inventory_plan,
            "high_risk_items": len([item for item in inventory_plan if item["stockout_risk"] >= 40]),
        }
        scenario.status = JOB_COMPLETED
        db.commit()
        db.refresh(scenario)
        return scenario

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        scenario = db.get(Scenario, scenario.id)
        scenario.status = JOB_FAILED
        scenario.error_message = str(exc)[:1000]
        db.commit()
        db.refresh(scenario)
        return scenario


def get_scenario_points(db: Session, scenario_id: int) -> list[dict]:
    rows = (
        db.query(ScenarioResult)
        .filter(ScenarioResult.scenario_id == scenario_id)
        .order_by(ScenarioResult.forecast_date.asc())
        .all()
    )
    buckets: dict[str, dict] = defaultdict(lambda: {"baseline": 0.0, "scenario": 0.0})
    for row in rows:
        bucket = buckets[row.forecast_date]
        bucket["baseline"] += float(row.baseline_yhat)
        bucket["scenario"] += float(row.scenario_yhat)

    points = []
    for date_str in sorted(buckets):
        bucket = buckets[date_str]
        baseline = bucket["baseline"]
        scenario_value = bucket["scenario"]
        delta_pct = ((scenario_value - baseline) / baseline * 100.0) if baseline else 0.0
        points.append(
            {
                "forecast_date": date_str,
                "baseline_yhat": safe_round(baseline, 2),
                "scenario_yhat": safe_round(scenario_value, 2),
                "delta_pct": safe_round(delta_pct, 2),
            }
        )
    return points
