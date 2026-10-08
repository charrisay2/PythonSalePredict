"""Lớp AI giải thích: xây ngữ cảnh cơ sở, gọi LLM, hậu kiểm số liệu, cache kết quả."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.fallback import build_fallback_explanation
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ai.providers import call_llm
from app.core.config import settings
from app.core.constants import JOB_COMPLETED, MODEL_LABELS
from app.core.utils import safe_round, stable_hash
from app.ml.decomposition import dow_label
from app.models import AIExplanation, Forecast, ForecastRun, Holiday, Product, Promo, Region
from app.services.forecasting import aggregate_points_by_date
from app.services.inventory import compute_inventory_plan

STOCKOUT_RISK_THRESHOLD = 40.0
OVERSTOCK_RISK_THRESHOLD = 60.0

# Bắt cả số có dấu phân cách nghìn (1,200.5) lẫn số thập phân thường (12.5)
NUMBER_PATTERN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def _parse_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Xây ngữ cảnh (grounded context)
# ---------------------------------------------------------------------------
def _upcoming_promos(db: Session, start: str, end: str) -> list[dict]:
    promos = db.query(Promo).filter(Promo.end_date >= start, Promo.start_date <= end).all()
    return [
        {
            "name": promo.name,
            "start_date": promo.start_date,
            "end_date": promo.end_date,
            "discount_pct": safe_round(promo.discount_pct, 2),
            "uplift_factor": safe_round(promo.uplift_factor, 3),
        }
        for promo in promos[:5]
    ]


def _upcoming_holidays(db: Session, start: str, end: str) -> list[dict]:
    holidays = db.query(Holiday).all()
    month_days = {start[5:], end[5:]}
    matched = []
    for holiday in holidays:
        in_window = start <= holiday.holiday_date <= end
        recurring = holiday.is_recurring_yearly and (
            holiday.holiday_date[5:] >= start[5:] and holiday.holiday_date[5:] <= end[5:]
        )
        if in_window or recurring or holiday.holiday_date[5:] in month_days:
            matched.append(
                {
                    "name": holiday.name,
                    "holiday_date": holiday.holiday_date,
                    "impact_factor": safe_round(holiday.impact_factor, 3),
                }
            )
    return matched[:5]


def build_context(db: Session, run: ForecastRun) -> dict:
    metrics = run.metrics or {}
    drivers = run.drivers or {}

    points = db.query(Forecast).filter(Forecast.run_id == run.id).all()
    by_date = aggregate_points_by_date(points)
    horizon_days = len(by_date)
    totals = [float(item["yhat"]) for item in by_date]
    total_units = sum(totals)
    avg_daily = total_units / horizon_days if horizon_days else 0.0
    peak = max(by_date, key=lambda item: item["yhat"]) if by_date else None
    half = max(1, horizon_days // 2)
    first_half = sum(totals[:half])
    second_half = sum(totals[half:])
    trend_pct = ((second_half - first_half) / first_half * 100.0) if first_half else 0.0

    plan = compute_inventory_plan(db, run.id)
    risks = [item for item in plan if item["stockout_risk"] >= STOCKOUT_RISK_THRESHOLD][:5]
    overstocks = [item for item in plan if item["overstock_risk"] >= OVERSTOCK_RISK_THRESHOLD][:5]

    start_date = by_date[0]["forecast_date"] if by_date else None
    end_date = by_date[-1]["forecast_date"] if by_date else None

    context = {
        "run": {
            "id": run.id,
            "name": run.name,
            "model": run.model_name,
            "model_label": MODEL_LABELS.get(run.model_name, run.model_name),
            "granularity": run.granularity,
            "horizon": run.horizon,
            "train_start": run.train_start,
            "train_end": run.train_end,
            "forecast_start": start_date,
            "forecast_end": end_date,
        },
        "metrics": {
            "mape": metrics.get("mape"),
            "smape": metrics.get("smape"),
            "rmse": metrics.get("rmse"),
            "mae": metrics.get("mae"),
            "bias": metrics.get("bias"),
            "accuracy": metrics.get("accuracy"),
        },
        "drivers": {
            "baseline_mean": drivers.get("baseline_mean"),
            "trend_delta_units": drivers.get("trend_delta_units"),
            "trend_delta_pct": drivers.get("trend_delta_pct"),
            "weekly_amplitude_units": drivers.get("weekly_amplitude_units"),
            "weekly_amplitude_pct": drivers.get("weekly_amplitude_pct"),
            "best_dayofweek_label": dow_label(int(drivers.get("best_dayofweek", 0))),
            "worst_dayofweek_label": dow_label(int(drivers.get("worst_dayofweek", 0))),
            "holiday_lift_units": drivers.get("holiday_lift_units"),
            "holiday_lift_pct": drivers.get("holiday_lift_pct"),
            "promo_lift_units": drivers.get("promo_lift_units"),
            "promo_lift_pct": drivers.get("promo_lift_pct"),
            "price_change_pct": drivers.get("price_change_pct"),
            "n_observations": drivers.get("n_observations"),
        },
        "forecast_summary": {
            "total_units": safe_round(total_units, 2),
            "avg_daily": safe_round(avg_daily, 2),
            "peak_date": peak["forecast_date"] if peak else None,
            "peak_units": safe_round(peak["yhat"], 2) if peak else 0.0,
            "first_half_units": safe_round(first_half, 2),
            "second_half_units": safe_round(second_half, 2),
            "trend_pct": safe_round(trend_pct, 2),
            "n_series": len({(p.product_id, p.region_id, p.channel_id) for p in points}),
        },
        "top_inventory_risks": [
            {
                "product_name": item.get("product_name"),
                "region_name": item.get("region_name"),
                "stockout_risk": item.get("stockout_risk"),
                "forecast_units": item.get("forecast_units"),
                "daily_demand": item.get("daily_demand"),
                "lead_time_days": item.get("lead_time_days"),
                "lead_time_demand": item.get("lead_time_demand"),
                "on_hand_qty": item.get("on_hand_qty"),
                "incoming_qty": item.get("incoming_qty"),
                "safety_stock": item.get("safety_stock"),
                "reorder_point": item.get("reorder_point"),
                "suggested_order_qty": item.get("suggested_order_qty"),
            }
            for item in risks
        ],
        "overstock_items": [
            {
                "product_name": item.get("product_name"),
                "region_name": item.get("region_name"),
                "overstock_risk": item.get("overstock_risk"),
                "forecast_units": item.get("forecast_units"),
                "on_hand_qty": item.get("on_hand_qty"),
            }
            for item in overstocks
        ],
        "upcoming_promos": _upcoming_promos(db, start_date, end_date) if start_date else [],
        "upcoming_holidays": _upcoming_holidays(db, start_date, end_date) if start_date else [],
        "inventory_plan_size": len(plan),
    }
    return context


# ---------------------------------------------------------------------------
# Hậu kiểm số liệu (grounding check)
# ---------------------------------------------------------------------------
def _collect_numbers(value, sink: set[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_numbers(item, sink)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_numbers(item, sink)
    elif isinstance(value, (int, float)):
        number = float(value)
        for digits in (0, 1, 2):
            sink.add(round(number, digits))
    elif isinstance(value, str):
        # Cho phép các con số nằm trong chuỗi (ví dụ ngày "2026-11-28" -> 2026, 11, 28)
        for match in NUMBER_PATTERN.findall(value):
            parsed = _parse_number(match)
            if parsed is None:
                continue
            for digits in (0, 1, 2):
                sink.add(round(parsed, digits))


def _is_grounded(number: float, allowed: set[float]) -> bool:
    if 1900 <= number <= 2100:  # năm
        return True
    for candidate in allowed:
        if abs(number - candidate) <= max(0.5, abs(number) * 0.03):
            return True
    return False


def validate_grounding(payload: dict, context: dict) -> list[str]:
    allowed: set[float] = set()
    _collect_numbers(context, allowed)

    texts: list[str] = [str(payload.get("summary") or "")]
    for reason in payload.get("reasons") or []:
        texts.append(str(reason.get("evidence") or ""))
        texts.append(str(reason.get("factor") or ""))
    for action in payload.get("recommended_actions") or []:
        texts.append(str(action.get("rationale") or ""))
        texts.append(str(action.get("action") or ""))

    warnings: list[str] = []
    for text in texts:
        for match in NUMBER_PATTERN.findall(text):
            number = _parse_number(match)
            if number is None:
                continue
            if not _is_grounded(number, allowed):
                warnings.append(f"Số liệu '{match}' không khớp với dữ liệu gốc.")
    # loại trùng, giới hạn số lượng cảnh báo
    unique: list[str] = []
    for item in warnings:
        if item not in unique:
            unique.append(item)
    return unique[:8]


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _normalise_payload(payload: dict) -> dict:
    reasons = []
    for item in payload.get("reasons") or []:
        if not isinstance(item, dict):
            continue
        direction = str(item.get("direction", "flat")).lower()
        if direction not in ("up", "down", "flat"):
            direction = "flat"
        try:
            magnitude = float(item.get("magnitude_pct", 0) or 0)
        except (TypeError, ValueError):
            magnitude = 0.0
        reasons.append(
            {
                "factor": str(item.get("factor", "Yếu tố khác")),
                "direction": direction,
                "magnitude_pct": safe_round(abs(magnitude), 2),
                "evidence": str(item.get("evidence", "")),
            }
        )

    actions = []
    for item in payload.get("recommended_actions") or []:
        if not isinstance(item, dict):
            continue
        priority = str(item.get("priority", "medium")).lower()
        if priority not in ("low", "medium", "high"):
            priority = "medium"
        actions.append(
            {
                "action": str(item.get("action", "")),
                "rationale": str(item.get("rationale", "")),
                "priority": priority,
                "owner": str(item.get("owner", "")),
            }
        )

    confidence = str(payload.get("confidence", "medium")).lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "medium"

    return {
        "summary": str(payload.get("summary", "")),
        "reasons": reasons,
        "recommended_actions": actions,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Điểm vào chính
# ---------------------------------------------------------------------------
def explain_run(db: Session, request, user_id: int | None = None) -> dict:
    run = db.get(ForecastRun, request.run_id)
    if run is None:
        raise ValueError("Không tìm thấy lần dự báo")
    if run.status != JOB_COMPLETED:
        raise ValueError("Lần dự báo chưa hoàn thành, chưa thể giải thích")

    context = build_context(db, run)
    cache_key = stable_hash(
        {
            "context": context,
            "question": request.question,
            "provider": settings.llm_provider,
            "language": request.language,
        }
    )

    if not request.force_refresh:
        cached = db.query(AIExplanation).filter(AIExplanation.prompt_hash == cache_key).first()
        if cached and cached.content:
            return {**cached.content, "cached": True, "provider": cached.provider, "run_id": run.id}

    grounded_numbers = {
        "total_forecast_units": context["forecast_summary"]["total_units"],
        "avg_daily_units": context["forecast_summary"]["avg_daily"],
        "mape": context["metrics"]["mape"],
        "accuracy": context["metrics"]["accuracy"],
        "trend_delta_pct": context["drivers"]["trend_delta_pct"],
        "promo_lift_units": context["drivers"]["promo_lift_units"],
        "holiday_lift_units": context["drivers"]["holiday_lift_units"],
        "high_risk_items": len(context["top_inventory_risks"]),
    }

    provider = "fallback"
    warnings: list[str] = []
    payload: dict | None = None
    raw_text = ""

    if settings.llm_enabled:
        user_prompt = build_user_prompt(context, request.question)
        result = call_llm(SYSTEM_PROMPT, user_prompt)
        if result.ok:
            raw_text = result.text
            parsed = _extract_json(result.text)
            if parsed is not None:
                normalised = _normalise_payload(parsed)
                warnings = validate_grounding(normalised, context)
                if warnings and not normalised["summary"]:
                    warnings.append("Phản hồi của mô hình không đầy đủ, đã bổ sung bằng giải thích nội bộ.")
                payload = normalised
                provider = result.provider
            else:
                warnings.append("Không đọc được JSON từ mô hình, đã dùng giải thích nội bộ.")
        else:
            warnings.append(f"Gọi LLM thất bại ({result.error}). Đã dùng giải thích nội bộ.")

    if payload is None:
        payload = build_fallback_explanation(context)
        provider = "fallback"

    payload["grounded_numbers"] = grounded_numbers
    payload["warnings"] = warnings
    payload["cached"] = False
    payload["run_id"] = run.id
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()

    record = AIExplanation(
        prompt_hash=cache_key,
        scope="forecast",
        run_id=run.id,
        provider=provider,
        content={key: value for key, value in payload.items() if key != "generated_at"},
        raw_text=raw_text[:8000] if raw_text else None,
    )
    db.add(record)
    db.commit()

    return {**payload, "provider": provider}
