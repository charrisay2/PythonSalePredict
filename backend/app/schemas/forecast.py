"""Pydantic schema cho huấn luyện / dự báo / so sánh mô hình."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import ALL_MODELS, DEFAULT_MODELS


class ForecastScope(BaseModel):
    product_ids: list[int] | None = None
    region_ids: list[int] | None = None
    channel_ids: list[int] | None = None


class TrainRequest(ForecastScope):
    name: str | None = None
    models: list[str] | None = None
    horizon: int = Field(default=30, ge=1, le=180)
    # total | product | region | channel | product_region
    granularity: str = "total"
    backtest_folds: int = Field(default=3, ge=1, le=8)
    test_size: int = Field(default=28, ge=7, le=120)
    wait: bool = False

    @field_validator("models")
    @classmethod
    def _validate_models(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return list(DEFAULT_MODELS)
        unknown = [m for m in value if m not in ALL_MODELS]
        if unknown:
            raise ValueError(f"Mô hình không hỗ trợ: {unknown}. Hỗ trợ: {list(ALL_MODELS)}")
        return value or list(DEFAULT_MODELS)

    @field_validator("granularity")
    @classmethod
    def _validate_granularity(cls, value: str) -> str:
        allowed = {"total", "product", "region", "channel", "product_region"}
        if value not in allowed:
            raise ValueError(f"granularity phải thuộc {sorted(allowed)}")
        return value


class ForecastPoint(BaseModel):
    forecast_date: str
    product_id: int | None = None
    region_id: int | None = None
    channel_id: int | None = None
    yhat: float
    yhat_lower: float
    yhat_upper: float


class LeaderboardEntry(BaseModel):
    model_name: str
    label: str
    mape: float
    smape: float
    rmse: float
    mae: float
    bias: float
    rank: int = 0
    is_best: bool = False
    note: str | None = None


class ForecastRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    model_name: str
    horizon: int
    granularity: str
    scope: dict | None = None
    params: dict | None = None
    metrics: dict | None = None
    leaderboard: list | None = None
    drivers: dict | None = None
    train_start: str | None = None
    train_end: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class HistoryPoint(BaseModel):
    ds: str
    y: float


class ForecastResponse(BaseModel):
    run: ForecastRunOut
    points: list[ForecastPoint] = Field(default_factory=list)
    history: list[HistoryPoint] = Field(default_factory=list)
    total_forecast_units: float = 0.0


class CompareRequest(ForecastScope):
    models: list[str] | None = None
    horizon: int = Field(default=30, ge=1, le=180)
    granularity: str = "total"
    backtest_folds: int = Field(default=3, ge=1, le=8)
    test_size: int = Field(default=28, ge=7, le=120)

    @field_validator("models")
    @classmethod
    def _validate_models(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return list(DEFAULT_MODELS)
        unknown = [m for m in value if m not in ALL_MODELS]
        if unknown:
            raise ValueError(f"Mô hình không hỗ trợ: {unknown}")
        return value or list(DEFAULT_MODELS)


class CompareResponse(BaseModel):
    run: ForecastRunOut
    leaderboard: list[LeaderboardEntry] = Field(default_factory=list)
