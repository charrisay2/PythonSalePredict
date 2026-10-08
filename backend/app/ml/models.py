"""Các mô hình dự báo: baseline, Prophet, scikit-learn (lag features), SARIMA."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.core.constants import (
    MODEL_GRADIENT_BOOSTING,
    MODEL_MOVING_AVERAGE,
    MODEL_NAIVE,
    MODEL_PROPHET,
    MODEL_RANDOM_FOREST,
    MODEL_SARIMA,
    MODEL_SEASONAL_NAIVE,
)
from app.ml.base import REGRESSOR_COLUMNS, BaseForecaster, ForecastOutput
from app.ml.features import feature_names, lag_feature_row

MIN_POINTS = 30


def _as_float_array(values) -> np.ndarray:
    return np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)


def _to_datetime_list(values) -> list[pd.Timestamp]:
    return list(pd.to_datetime(pd.Series(list(values))))


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------
class NaiveForecaster(BaseForecaster):
    name = MODEL_NAIVE
    label = "Naive (kỳ trước)"

    def fit(self, history: pd.DataFrame, future: pd.DataFrame) -> "NaiveForecaster":
        y = _as_float_array(history["y"])
        if y.size < 2:
            raise ValueError("Naive cần ít nhất 2 điểm dữ liệu")
        self.history, self.future = history, future
        self.last_value = float(y[-1])
        fitted = np.concatenate([[self.last_value], y[:-1]])
        self.resid_std = self._residual_std(history, fitted)
        return self

    def predict(self) -> ForecastOutput:
        horizon = len(self.future)
        yhat = np.full(horizon, self.last_value, dtype=float)
        lower, upper = self._interval(yhat, self.resid_std, horizon)
        return ForecastOutput(yhat=yhat, lower=lower, upper=upper)


class SeasonalNaiveForecaster(BaseForecaster):
    name = MODEL_SEASONAL_NAIVE
    label = "Seasonal Naive (lag 7)"
    season = 7

    def fit(self, history: pd.DataFrame, future: pd.DataFrame) -> "SeasonalNaiveForecaster":
        y = _as_float_array(history["y"])
        if y.size < self.season + 1:
            raise ValueError(f"Seasonal Naive cần ít nhất {self.season + 1} điểm dữ liệu")
        self.history, self.future = history, future
        fitted = np.concatenate([np.full(self.season, y[0]), y[: -self.season]])
        self.resid_std = self._residual_std(history, fitted)
        self.season_values = y[-self.season :]
        return self

    def predict(self) -> ForecastOutput:
        horizon = len(self.future)
        repeats = int(math.ceil(horizon / self.season))
        yhat = np.tile(self.season_values, repeats)[:horizon].astype(float)
        lower, upper = self._interval(yhat, self.resid_std, horizon)
        return ForecastOutput(yhat=yhat, lower=lower, upper=upper)


class MovingAverageForecaster(BaseForecaster):
    name = MODEL_MOVING_AVERAGE
    label = "Moving Average (28 kỳ)"

    def __init__(self, window: int = 28, **params):
        super().__init__(window=window, **params)
        self.window = window

    def fit(self, history: pd.DataFrame, future: pd.DataFrame) -> "MovingAverageForecaster":
        y = _as_float_array(history["y"])
        if y.size < MIN_POINTS:
            raise ValueError(f"Moving Average cần ít nhất {MIN_POINTS} điểm dữ liệu")
        self.history, self.future = history, future
        window = min(self.window, y.size - 1)
        fitted = np.array(
            [np.mean(y[max(0, i - window) : i]) if i > 0 else y[0] for i in range(y.size)]
        )
        self.resid_std = self._residual_std(history, fitted)
        self.level = float(np.mean(y[-window:]))
        return self

    def predict(self) -> ForecastOutput:
        horizon = len(self.future)
        yhat = np.full(horizon, self.level, dtype=float)
        lower, upper = self._interval(yhat, self.resid_std, horizon)
        return ForecastOutput(yhat=yhat, lower=lower, upper=upper)


# --------------------------------------------------------------------------
# scikit-learn: hồi quy trên đặc trưng lag + lịch + ngoại sinh (dự báo đệ quy)
# --------------------------------------------------------------------------
class SklearnForecaster(BaseForecaster):
    supports_regressors = True

    def __init__(
        self,
        kind: str = MODEL_GRADIENT_BOOSTING,
        lags: tuple[int, ...] = (1, 7, 14, 28),
        rolling_windows: tuple[int, ...] = (7, 28),
        **params,
    ):
        super().__init__(**params)
        self.kind = kind
        self.lags = tuple(lags)
        self.rolling_windows = tuple(rolling_windows)
        self.columns = feature_names(self.lags, self.rolling_windows)
        self.model = None
        self.resid_std = 0.0
        self.feature_importance: dict[str, float] = {}
        self.history: pd.DataFrame | None = None
        self.future: pd.DataFrame | None = None

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.kind

    @property
    def label(self) -> str:  # type: ignore[override]
        if self.kind == MODEL_RANDOM_FOREST:
            return "Random Forest (đặc trưng trễ)"
        return "Gradient Boosting (đặc trưng trễ)"

    def _make_estimator(self):
        if self.kind == MODEL_RANDOM_FOREST:
            from sklearn.ensemble import RandomForestRegressor

            return RandomForestRegressor(
                n_estimators=300, max_depth=8, min_samples_leaf=2, random_state=42, n_jobs=-1
            )
        from sklearn.ensemble import GradientBoostingRegressor

        return GradientBoostingRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=3, random_state=42
        )

    def _build_matrix(
        self, values: np.ndarray, ds_values: list[pd.Timestamp], regressors: pd.DataFrame
    ) -> pd.DataFrame:
        rows = []
        for index in range(len(values)):
            reg_row = regressors.iloc[index].to_dict() if index < len(regressors) else {}
            rows.append(
                lag_feature_row(
                    values[:index], ds_values[index], reg_row, self.lags, self.rolling_windows
                )
            )
        return pd.DataFrame(rows, columns=self.columns)

    def fit(self, history: pd.DataFrame, future: pd.DataFrame) -> "SklearnForecaster":
        y = _as_float_array(history["y"])
        if y.size < MIN_POINTS + 30:
            raise ValueError(f"Mô hình ML cần ít nhất {MIN_POINTS + 30} điểm dữ liệu")
        self.history, self.future = history, future
        ds_values = _to_datetime_list(history["ds"])
        regressors = history[[c for c in REGRESSOR_COLUMNS if c in history.columns]].reset_index(drop=True)

        matrix = self._build_matrix(y, ds_values, regressors)
        mask = matrix.notna().all(axis=1).to_numpy()
        matrix = matrix[mask]
        y_train = y[mask]
        if y_train.size < MIN_POINTS:
            raise ValueError("Không đủ dữ liệu hợp lệ sau khi tạo đặc trưng lag")

        self.model = self._make_estimator()
        self.model.fit(matrix, y_train)
        fitted = self.model.predict(matrix)
        self.resid_std = self._residual_std(pd.DataFrame({"y": y_train}), fitted)
        if hasattr(self.model, "feature_importances_"):
            self.feature_importance = {
                column: float(value)
                for column, value in zip(self.columns, self.model.feature_importances_)
            }
        return self

    def predict(self) -> ForecastOutput:
        horizon = len(self.future)
        values = list(_as_float_array(self.history["y"]))
        ds_values = _to_datetime_list(self.future["ds"])
        regressors = self.future[[c for c in REGRESSOR_COLUMNS if c in self.future.columns]].reset_index(
            drop=True
        )

        predictions: list[float] = []
        for step in range(horizon):
            reg_row = regressors.iloc[step].to_dict() if step < len(regressors) else {}
            row = lag_feature_row(
                np.asarray(values, dtype=float),
                ds_values[step],
                reg_row,
                self.lags,
                self.rolling_windows,
            )
            features = pd.DataFrame([row], columns=self.columns).fillna(0.0)
            predicted = float(self.model.predict(features)[0])
            predicted = max(0.0, predicted)
            predictions.append(predicted)
            values.append(predicted)

        yhat = np.asarray(predictions, dtype=float)
        lower, upper = self._interval(yhat, self.resid_std, horizon)
        return ForecastOutput(yhat=yhat, lower=lower, upper=upper)


class GradientBoostingForecaster(SklearnForecaster):
    def __init__(self, **params):
        super().__init__(kind=MODEL_GRADIENT_BOOSTING, **params)


class RandomForestForecaster(SklearnForecaster):
    def __init__(self, **params):
        super().__init__(kind=MODEL_RANDOM_FOREST, **params)


# --------------------------------------------------------------------------
# Prophet
# --------------------------------------------------------------------------
class ProphetForecaster(BaseForecaster):
    name = MODEL_PROPHET
    label = "Prophet (xu hướng + mùa vụ)"
    supports_regressors = True

    def __init__(self, **params):
        super().__init__(**params)
        self.model = None
        self.regressors: list[str] = []
        self.history: pd.DataFrame | None = None
        self.future: pd.DataFrame | None = None

    def fit(self, history: pd.DataFrame, future: pd.DataFrame) -> "ProphetForecaster":
        from prophet import Prophet  # import muộn: prophet là tùy chọn

        if len(history) < MIN_POINTS:
            raise ValueError(f"Prophet cần ít nhất {MIN_POINTS} điểm dữ liệu")
        self.history, self.future = history, future

        frame = pd.DataFrame(
            {
                "ds": pd.to_datetime(pd.Series(list(history["ds"]))),
                "y": _as_float_array(history["y"]),
            }
        )
        self.regressors = []
        for column in REGRESSOR_COLUMNS:
            if column in history.columns:
                frame[column] = _as_float_array(history[column])
                self.regressors.append(column)

        model = Prophet(
            weekly_seasonality=True,
            yearly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.95,
            changepoint_prior_scale=0.05,
            seasonality_mode="additive",
        )
        for column in self.regressors:
            model.add_regressor(column)
        model.fit(frame)
        self.model = model
        return self

    def predict(self) -> ForecastOutput:
        horizon = len(self.future)
        frame = pd.DataFrame({"ds": pd.to_datetime(pd.Series(list(self.future["ds"])))})
        for column in self.regressors:
            if column in self.future.columns:
                frame[column] = _as_float_array(self.future[column])
            else:
                frame[column] = 0.0

        forecast = self.model.predict(frame)
        yhat = np.clip(forecast["yhat"].to_numpy(dtype=float), 0.0, None)
        lower = np.clip(forecast["yhat_lower"].to_numpy(dtype=float), 0.0, None)
        upper = np.clip(forecast["yhat_upper"].to_numpy(dtype=float), 0.0, None)

        drivers = {}
        for component in ("trend", "weekly", "yearly"):
            if component in forecast.columns:
                drivers[component] = float(np.mean(forecast[component].to_numpy(dtype=float)))
        if horizon and horizon != len(forecast):
            pass
        return ForecastOutput(yhat=yhat, lower=lower, upper=upper, drivers=drivers)


# --------------------------------------------------------------------------
# SARIMA
# --------------------------------------------------------------------------
class SarimaForecaster(BaseForecaster):
    name = MODEL_SARIMA
    label = "SARIMA (statsmodels)"

    def __init__(self, order=(1, 1, 1), seasonal_order=(1, 0, 1, 7), **params):
        super().__init__(**params)
        self.order = order
        self.seasonal_order = seasonal_order
        self.result = None
        self.history: pd.DataFrame | None = None
        self.future: pd.DataFrame | None = None

    def fit(self, history: pd.DataFrame, future: pd.DataFrame) -> "SarimaForecaster":
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        y = _as_float_array(history["y"])
        if y.size < 90:
            raise ValueError("SARIMA cần ít nhất 90 điểm dữ liệu")
        self.history, self.future = history, future
        model = SARIMAX(
            y,
            order=self.order,
            seasonal_order=self.seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        self.result = model.fit(disp=False, maxiter=60)
        return self

    def predict(self) -> ForecastOutput:
        horizon = len(self.future)
        forecast = self.result.get_forecast(steps=horizon)
        yhat = np.clip(np.asarray(forecast.predicted_mean, dtype=float), 0.0, None)
        conf_int = np.asarray(forecast.conf_int(alpha=0.05), dtype=float)
        lower = np.clip(conf_int[:, 0], 0.0, None)
        upper = np.clip(conf_int[:, 1], 0.0, None)
        return ForecastOutput(yhat=yhat, lower=lower, upper=upper)
