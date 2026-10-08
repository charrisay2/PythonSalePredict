"""Kiểm thử lớp AI giải thích: đảm bảo chỉ dùng số liệu được cung cấp."""

from __future__ import annotations

from app.ai.explainer import validate_grounding
from app.ai.fallback import build_fallback_explanation
from app.ml.decomposition import compute_drivers

import pandas as pd
import numpy as np


def _context() -> dict:
    return {
        "run": {"id": 1, "model_label": "Prophet", "horizon": 30, "granularity": "product"},
        "metrics": {"mape": 8.5, "smape": 9.1, "rmse": 12.0, "mae": 9.0, "bias": 1.2, "accuracy": 91.5},
        "drivers": {
            "trend_delta_units": 15.0,
            "trend_delta_pct": 12.5,
            "weekly_amplitude_units": 40.0,
            "weekly_amplitude_pct": 33.3,
            "best_dayofweek": 5,
            "worst_dayofweek": 1,
            "holiday_lift_units": 25.0,
            "holiday_lift_pct": 20.8,
            "promo_lift_units": 60.0,
            "promo_lift_pct": 50.0,
        },
        "forecast_summary": {
            "total_units": 1200.0,
            "avg_daily": 40.0,
            "peak_date": "2026-11-28",
            "peak_units": 75.0,
            "trend_pct": 8.0,
        },
        "top_inventory_risks": [
            {
                "product_name": "Trà xanh",
                "region_name": "Miền Bắc",
                "stockout_risk": 72.0,
                "forecast_units": 300.0,
                "daily_demand": 10.0,
                "lead_time_days": 5,
                "lead_time_demand": 50.0,
                "on_hand_qty": 14.0,
                "incoming_qty": 0.0,
                "safety_stock": 6.0,
                "reorder_point": 56.0,
                "suggested_order_qty": 42.0,
            }
        ],
        "overstock_items": [],
        "upcoming_promos": [
            {
                "name": "Black Friday",
                "start_date": "2026-11-20",
                "end_date": "2026-11-30",
                "discount_pct": 25.0,
                "uplift_factor": 1.5,
            }
        ],
        "upcoming_holidays": [{"name": "Giáng sinh", "holiday_date": "2026-12-24", "impact_factor": 1.45}],
    }


def test_fallback_explanation_has_required_shape():
    payload = build_fallback_explanation(_context())
    assert payload["summary"]
    assert payload["reasons"]
    assert payload["recommended_actions"]
    assert payload["confidence"] in {"low", "medium", "high"}


def test_fallback_explanation_is_fully_grounded():
    """Giải thích nội bộ không được phép sinh ra con số ngoài ngữ cảnh."""
    context = _context()
    payload = build_fallback_explanation(context)
    assert validate_grounding(payload, context) == []


def test_grounding_detects_invented_numbers():
    context = _context()
    payload = build_fallback_explanation(context)
    payload["summary"] = "Nhu cầu dự báo sẽ tăng 987654% trong tháng tới."
    warnings = validate_grounding(payload, context)
    assert warnings, "Phải phát hiện được con số không có trong ngữ cảnh"


def test_grounding_allows_years():
    context = _context()
    payload = {"summary": "Dự báo cho năm 2026", "reasons": [], "recommended_actions": []}
    assert validate_grounding(payload, context) == []


def test_compute_drivers_detects_promo_effect():
    dates = pd.date_range("2026-01-01", periods=120, freq="D")
    values = np.full(120, 100.0)
    promo = np.ones(120)
    promo[60:] = 1.5
    values[60:] = 150.0

    frame = pd.DataFrame(
        {
            "ds": dates,
            "y": values,
            "promo_uplift": promo,
            "discount_pct": np.where(promo > 1, 20.0, 0.0),
            "unit_price": np.full(120, 10000.0),
            "holiday_impact": np.ones(120),
        }
    )
    drivers = compute_drivers(frame)
    assert drivers["promo_lift_units"] > 0
    assert drivers["n_observations"] == 120
