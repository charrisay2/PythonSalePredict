"""Phân rã thành phần đóng góp vào nhu cầu (trend, mùa vụ, ngày lễ, khuyến mãi).

Kết quả được dùng làm đầu vào CƠ SỞ SỐ LIỆU cho lớp AI giải thích.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.utils import safe_round


def _mean(values) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if arr.size else 0.0


def compute_drivers(history: pd.DataFrame) -> dict:
    """`history` gồm các cột: ds (datetime), y, promo_uplift, discount_pct, holiday_impact, unit_price."""
    if history is None or history.empty:
        return {}

    frame = history.copy()
    frame["ds"] = pd.to_datetime(frame["ds"])
    frame = frame.sort_values("ds").reset_index(drop=True)
    y = frame["y"].to_numpy(dtype=float)
    overall_mean = _mean(y)

    # --- Trend: so sánh trung bình 28 ngày cuối với 28 ngày trước đó ---
    recent = _mean(y[-28:]) if y.size >= 28 else _mean(y)
    previous = _mean(y[-56:-28]) if y.size >= 56 else _mean(y[: max(1, y.size // 2)])
    trend_delta = recent - previous

    # --- Mùa vụ theo thứ trong tuần ---
    frame["dow"] = frame["ds"].dt.dayofweek
    dow_mean = frame.groupby("dow")["y"].mean()
    weekly_amplitude = float(dow_mean.max() - dow_mean.min()) if len(dow_mean) > 1 else 0.0
    best_dow = int(dow_mean.idxmax()) if len(dow_mean) else 0
    worst_dow = int(dow_mean.idxmin()) if len(dow_mean) else 0

    # --- Ngày lễ ---
    holiday_mask = frame.get("holiday_impact", pd.Series(1.0, index=frame.index)).to_numpy(dtype=float) > 1.001
    if holiday_mask.any():
        holiday_mean = _mean(y[holiday_mask])
        non_holiday_mean = _mean(y[~holiday_mask])
        holiday_lift = holiday_mean - non_holiday_mean
    else:
        holiday_lift = 0.0

    # --- Khuyến mãi ---
    promo_mask = frame.get("promo_uplift", pd.Series(1.0, index=frame.index)).to_numpy(dtype=float) > 1.001
    if promo_mask.any():
        promo_mean = _mean(y[promo_mask])
        non_promo_mean = _mean(y[~promo_mask])
        promo_lift = promo_mean - non_promo_mean
    else:
        promo_lift = 0.0

    # --- Giá ---
    price_delta = 0.0
    if "unit_price" in frame.columns and y.size >= 28:
        price_now = _mean(frame["unit_price"].to_numpy(dtype=float)[-28:])
        price_before = _mean(frame["unit_price"].to_numpy(dtype=float)[: max(1, y.size // 2)])
        if price_before > 0:
            price_delta = (price_now - price_before) / price_before * 100.0

    def pct(value: float) -> float:
        return safe_round(value / overall_mean * 100.0, 2) if overall_mean else 0.0

    return {
        "baseline_mean": safe_round(overall_mean, 2),
        "trend_delta_units": safe_round(trend_delta, 2),
        "trend_delta_pct": pct(trend_delta),
        "weekly_amplitude_units": safe_round(weekly_amplitude, 2),
        "weekly_amplitude_pct": pct(weekly_amplitude),
        "best_dayofweek": best_dow,
        "worst_dayofweek": worst_dow,
        "holiday_lift_units": safe_round(holiday_lift, 2),
        "holiday_lift_pct": pct(holiday_lift),
        "promo_lift_units": safe_round(promo_lift, 2),
        "promo_lift_pct": pct(promo_lift),
        "price_change_pct": safe_round(price_delta, 2),
        "n_observations": int(y.size),
    }


DOW_LABELS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def dow_label(index: int) -> str:
    if 0 <= index < len(DOW_LABELS_VI):
        return DOW_LABELS_VI[index]
    return "?"
