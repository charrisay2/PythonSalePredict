"""Chỉ số đánh giá sai số dự báo (MAPE, sMAPE, RMSE, MAE, Bias)."""

from __future__ import annotations

import numpy as np

EPS = 1e-9


def _arr(values) -> np.ndarray:
    return np.asarray(values, dtype=float).ravel()


def mae(y_true, y_pred) -> float:
    yt, yp = _arr(y_true), _arr(y_pred)
    if yt.size == 0:
        return 0.0
    return float(np.mean(np.abs(yt - yp)))


def rmse(y_true, y_pred) -> float:
    yt, yp = _arr(y_true), _arr(y_pred)
    if yt.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((yt - yp) ** 2)))


def bias(y_true, y_pred) -> float:
    """Dương = dự báo cao hơn thực tế (over-forecast)."""
    yt, yp = _arr(y_true), _arr(y_pred)
    if yt.size == 0:
        return 0.0
    return float(np.mean(yp - yt))


def mape(y_true, y_pred) -> float:
    """MAPE (%), bỏ qua các điểm thực tế = 0."""
    yt, yp = _arr(y_true), _arr(y_pred)
    mask = np.abs(yt) > EPS
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((yt[mask] - yp[mask]) / yt[mask])) * 100)


def smape(y_true, y_pred) -> float:
    """sMAPE (%) - ổn định hơn MAPE khi giá trị nhỏ."""
    yt, yp = _arr(y_true), _arr(y_pred)
    denom = np.abs(yt) + np.abs(yp)
    mask = denom > EPS
    if not mask.any():
        return 0.0
    return float(np.mean(2.0 * np.abs(yt[mask] - yp[mask]) / denom[mask]) * 100)


def coverage(y_true, y_lower, y_upper) -> float:
    """Tỷ lệ điểm thực tế nằm trong khoảng tin cậy (%)."""
    yt, lo, hi = _arr(y_true), _arr(y_lower), _arr(y_upper)
    if yt.size == 0:
        return 0.0
    inside = ((yt >= lo) & (yt <= hi)).sum()
    return float(inside / yt.size * 100)


def evaluate(y_true, y_pred, y_lower=None, y_upper=None) -> dict:
    yt, yp = _arr(y_true), _arr(y_pred)
    result = {
        "mape": round(mape(yt, yp), 2),
        "smape": round(smape(yt, yp), 2),
        "rmse": round(rmse(yt, yp), 2),
        "mae": round(mae(yt, yp), 2),
        "bias": round(bias(yt, yp), 2),
        "n_obs": int(yt.size),
    }
    if y_lower is not None and y_upper is not None:
        result["coverage"] = round(coverage(yt, y_lower, y_upper), 2)
    return result


def ranking_score(metrics: dict) -> float:
    """Điểm dùng để xếp hạng mô hình (nhỏ hơn = tốt hơn)."""
    mape_value = metrics.get("mape") or 0.0
    smape_value = metrics.get("smape") or 0.0
    if mape_value <= 0:
        return smape_value
    return mape_value


def accuracy_from_mape(mape_value: float | None) -> float | None:
    """Quy đổi MAPE thành độ chính xác (%) để hiển thị dashboard."""
    if mape_value is None:
        return None
    return round(max(0.0, min(100.0, 100.0 - float(mape_value))), 2)
