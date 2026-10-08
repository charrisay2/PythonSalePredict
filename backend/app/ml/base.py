"""Giao diện chung cho các mô hình dự báo chuỗi thời gian."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Các cột ngoại sinh (regressor) được dùng xuyên suốt hệ thống
REGRESSOR_COLUMNS = ("promo_uplift", "discount_pct", "unit_price", "holiday_impact")


@dataclass
class ForecastOutput:
    yhat: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    note: str = ""
    drivers: dict = field(default_factory=dict)


class BaseForecaster:
    """Mỗi mô hình nhận `history` (ds, y + regressors) và `future` (ds + regressors)."""

    name: str = "base"
    label: str = "Base"
    supports_regressors: bool = False

    def __init__(self, **params):
        self.params = params

    def fit(self, history: pd.DataFrame, future: pd.DataFrame) -> "BaseForecaster":
        raise NotImplementedError

    def predict(self) -> ForecastOutput:
        raise NotImplementedError

    # ---- Tiện ích dùng chung ----
    @staticmethod
    def _residual_std(history: pd.DataFrame, fitted: np.ndarray) -> float:
        y = history["y"].to_numpy(dtype=float)
        residuals = y - fitted
        std = float(np.std(residuals))
        if not np.isfinite(std) or std <= 0:
            std = max(1e-6, float(np.mean(np.abs(y))) * 0.1)
        return std

    @staticmethod
    def _interval(yhat: np.ndarray, std: float, horizon: int, z: float = 1.96):
        steps = np.arange(1, horizon + 1, dtype=float)
        scale = std * np.sqrt(1.0 + steps / 7.0)
        lower = np.maximum(0.0, yhat - z * scale)
        upper = yhat + z * scale
        return lower, upper
