"""Feature engineering cho chuỗi thời gian bán hàng."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Các cột ngoại sinh được đưa vào mô hình
REGRESSOR_COLUMNS = ("promo_uplift", "discount_pct", "unit_price", "holiday_impact")

CALENDAR_COLUMNS = (
    "dayofweek",
    "day",
    "month",
    "is_weekend",
    "doy_sin",
    "doy_cos",
    "dow_sin",
    "dow_cos",
)


def add_calendar_features(frame: pd.DataFrame, date_col: str = "ds") -> pd.DataFrame:
    """Thêm đặc trưng lịch (thứ, tháng, mùa vụ dạng sin/cos...)."""
    out = frame.copy()
    ds = pd.to_datetime(out[date_col])
    out["dayofweek"] = ds.dt.dayofweek
    out["day"] = ds.dt.day
    out["month"] = ds.dt.month
    out["quarter"] = ds.dt.quarter
    out["dayofyear"] = ds.dt.dayofyear
    out["is_weekend"] = (ds.dt.dayofweek >= 5).astype(int)
    out["doy_sin"] = np.sin(2 * np.pi * out["dayofyear"] / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * out["dayofyear"] / 365.25)
    out["dow_sin"] = np.sin(2 * np.pi * out["dayofweek"] / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * out["dayofweek"] / 7.0)
    return out


def calendar_row(ds_value: pd.Timestamp) -> dict:
    """Đặc trưng lịch cho một ngày (dùng khi dự báo đệ quy từng bước)."""
    doy = ds_value.dayofyear
    dow = ds_value.dayofweek
    return {
        "dayofweek": dow,
        "day": ds_value.day,
        "month": ds_value.month,
        "is_weekend": int(dow >= 5),
        "doy_sin": math.sin(2 * math.pi * doy / 365.25),
        "doy_cos": math.cos(2 * math.pi * doy / 365.25),
        "dow_sin": math.sin(2 * math.pi * dow / 7.0),
        "dow_cos": math.cos(2 * math.pi * dow / 7.0),
    }


def lag_feature_row(
    history_values: np.ndarray,
    ds_value: pd.Timestamp,
    regressor_row: dict,
    lags: tuple[int, ...] = (1, 7, 14, 28),
    rolling_windows: tuple[int, ...] = (7, 28),
) -> dict:
    """Một dòng đặc trưng (lag + rolling + lịch + ngoại sinh) tại thời điểm `ds_value`.

    `history_values` là toàn bộ giá trị đã biết TRƯỚC ngày cần dự báo.
    """
    n = len(history_values)
    row: dict[str, float] = {}
    for lag in lags:
        row[f"lag_{lag}"] = float(history_values[n - lag]) if n - lag >= 0 else np.nan
    for window in rolling_windows:
        chunk = history_values[max(0, n - window) : n]
        row[f"roll_mean_{window}"] = float(np.mean(chunk)) if chunk.size else np.nan
    row.update(calendar_row(ds_value))
    for column in REGRESSOR_COLUMNS:
        row[column] = float(regressor_row.get(column, 0.0) or 0.0)
    return row


def feature_names(lags: tuple[int, ...] = (1, 7, 14, 28), rolling_windows: tuple[int, ...] = (7, 28)) -> list[str]:
    names = [f"lag_{lag}" for lag in lags]
    names += [f"roll_mean_{w}" for w in rolling_windows]
    names += list(CALENDAR_COLUMNS)
    names += list(REGRESSOR_COLUMNS)
    return names
