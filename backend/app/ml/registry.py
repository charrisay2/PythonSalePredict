"""Factory tạo mô hình + kiểm tra khả dụng của thư viện tùy chọn."""

from __future__ import annotations

import importlib.util

from app.core.constants import (
    ALL_MODELS,
    MODEL_GRADIENT_BOOSTING,
    MODEL_LABELS,
    MODEL_MOVING_AVERAGE,
    MODEL_NAIVE,
    MODEL_PROPHET,
    MODEL_RANDOM_FOREST,
    MODEL_SARIMA,
    MODEL_SEASONAL_NAIVE,
)
from app.ml.base import BaseForecaster
from app.ml.models import (
    GradientBoostingForecaster,
    MovingAverageForecaster,
    NaiveForecaster,
    ProphetForecaster,
    RandomForestForecaster,
    SarimaForecaster,
    SeasonalNaiveForecaster,
)


def _spec_exists(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def prophet_available() -> bool:
    return _spec_exists("prophet")


def sarima_available() -> bool:
    return _spec_exists("statsmodels")


def sklearn_available() -> bool:
    return _spec_exists("sklearn")


def _unavailable_reason(model_name: str) -> str | None:
    if model_name == MODEL_PROPHET and not prophet_available():
        return "Thư viện `prophet` chưa được cài đặt (pip install prophet)"
    if model_name == MODEL_SARIMA and not sarima_available():
        return "Thư viện `statsmodels` chưa được cài đặt (pip install statsmodels)"
    if model_name in (MODEL_GRADIENT_BOOSTING, MODEL_RANDOM_FOREST) and not sklearn_available():
        return "Thư viện `scikit-learn` chưa được cài đặt"
    return None


def is_available(model_name: str) -> bool:
    return _unavailable_reason(model_name) is None


def build_forecaster(model_name: str, **kwargs) -> BaseForecaster:
    reason = _unavailable_reason(model_name)
    if reason:
        raise RuntimeError(reason)

    if model_name == MODEL_NAIVE:
        return NaiveForecaster(**kwargs)
    if model_name == MODEL_SEASONAL_NAIVE:
        return SeasonalNaiveForecaster(**kwargs)
    if model_name == MODEL_MOVING_AVERAGE:
        return MovingAverageForecaster(**kwargs)
    if model_name == MODEL_PROPHET:
        return ProphetForecaster(**kwargs)
    if model_name == MODEL_GRADIENT_BOOSTING:
        return GradientBoostingForecaster(**kwargs)
    if model_name == MODEL_RANDOM_FOREST:
        return RandomForestForecaster(**kwargs)
    if model_name == MODEL_SARIMA:
        return SarimaForecaster(**kwargs)
    raise ValueError(f"Mô hình không hỗ trợ: {model_name}")


def available_models() -> list[dict]:
    catalog = []
    for model_name in ALL_MODELS:
        reason = _unavailable_reason(model_name)
        catalog.append(
            {
                "name": model_name,
                "label": MODEL_LABELS.get(model_name, model_name),
                "available": reason is None,
                "reason": reason,
            }
        )
    return catalog
