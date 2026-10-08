"""Service dự báo: nạp dữ liệu, tạo chuỗi, backtest, huấn luyện và lưu kết quả."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.constants import (
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    MODEL_LABELS,
    MODEL_SEASONAL_NAIVE,
)
from app.core.utils import safe_round
from app.ml.backtest import rolling_origin_backtest
from app.ml.decomposition import compute_drivers
from app.ml.metrics import accuracy_from_mape, ranking_score
from app.ml.registry import build_forecaster, is_available
from app.models import Channel, Forecast, ForecastRun, Holiday, Product, Promo, Region, Sale

MAX_SERIES = 60

GRANULARITY_GROUPS: dict[str, list[str]] = {
    "total": [],
    "product": ["product_id"],
    "region": ["region_id"],
    "channel": ["channel_id"],
    "product_region": ["product_id", "region_id"],
}


# ---------------------------------------------------------------------------
# Nạp dữ liệu
# ---------------------------------------------------------------------------
def load_raw_sales(db: Session, scope: dict) -> pd.DataFrame:
    query = db.query(Sale)
    if scope.get("product_ids"):
        query = query.filter(Sale.product_id.in_(scope["product_ids"]))
    if scope.get("region_ids"):
        query = query.filter(Sale.region_id.in_(scope["region_ids"]))
    if scope.get("channel_ids"):
        query = query.filter(Sale.channel_id.in_(scope["channel_ids"]))

    rows = query.all()
    if not rows:
        return pd.DataFrame(
            columns=[
                "sale_date",
                "product_id",
                "region_id",
                "channel_id",
                "quantity",
                "revenue",
                "discount_pct",
                "unit_price",
            ]
        )
    return pd.DataFrame(
        [
            {
                "sale_date": row.sale_date,
                "product_id": row.product_id,
                "region_id": row.region_id,
                "channel_id": row.channel_id,
                "quantity": float(row.quantity),
                "revenue": float(row.revenue),
                "discount_pct": float(row.discount_pct),
                "unit_price": float(row.unit_price),
            }
            for row in rows
        ]
    )


def load_promos(db: Session) -> list[Promo]:
    return db.query(Promo).all()


def load_holidays(db: Session) -> list[Holiday]:
    return db.query(Holiday).all()


def _promo_uplift(promos: list[Promo], date_str: str, product_id, channel_id) -> tuple[float, float]:
    """Trả về (uplift_factor, discount_pct) lớn nhất áp dụng cho ngày/đối tượng này."""
    uplift, discount = 1.0, 0.0
    for promo in promos:
        if not (promo.start_date <= date_str <= promo.end_date):
            continue
        if promo.product_id is not None and product_id is not None and promo.product_id != product_id:
            continue
        if promo.channel_id is not None and channel_id is not None and promo.channel_id != channel_id:
            continue
        uplift = max(uplift, float(promo.uplift_factor))
        discount = max(discount, float(promo.discount_pct))
    return uplift, discount


def _holiday_impact(holidays: list[Holiday], date_str: str, region_id) -> float:
    impact = 1.0
    month_day = date_str[5:]
    for holiday in holidays:
        if holiday.region_id is not None and region_id is not None and holiday.region_id != region_id:
            continue
        matches = holiday.holiday_date == date_str or (
            holiday.is_recurring_yearly and holiday.holiday_date[5:] == month_day
        )
        if matches:
            impact = max(impact, float(holiday.impact_factor))
    return impact


# ---------------------------------------------------------------------------
# Tạo chuỗi
# ---------------------------------------------------------------------------
def build_series_frames(
    raw: pd.DataFrame,
    granularity: str,
    promos: list[Promo],
    holidays: list[Holiday],
) -> dict[str, pd.DataFrame]:
    """Trả về dict {series_key: DataFrame(ds, y, promo_uplift, discount_pct, unit_price, holiday_impact)}."""
    group_cols = GRANULARITY_GROUPS.get(granularity, [])
    if raw.empty:
        return {}

    aggregated = raw.groupby(["sale_date"] + group_cols, as_index=False).agg(
        y=("quantity", "sum"),
        revenue=("revenue", "sum"),
        discount_pct=("discount_pct", "mean"),
        unit_price=("unit_price", "mean"),
    )

    frames: dict[str, pd.DataFrame] = {}
    if group_cols:
        grouper = group_cols[0] if len(group_cols) == 1 else group_cols
        iterator = aggregated.groupby(grouper)
    else:
        iterator = [("__total__", aggregated)]

    promo_cache: dict[tuple, tuple[float, float]] = {}
    holiday_cache: dict[tuple, float] = {}

    for key, chunk in iterator:
        if not group_cols:
            product_id = region_id = channel_id = None
        else:
            if len(group_cols) == 1:
                value = key[0] if isinstance(key, tuple) else key
                product_id = int(value) if group_cols[0] == "product_id" else None
                region_id = int(value) if group_cols[0] == "region_id" else None
                channel_id = int(value) if group_cols[0] == "channel_id" else None
            else:
                product_id = int(key[0]) if "product_id" in group_cols else None
                region_id = int(key[1]) if "region_id" in group_cols else None
                channel_id = None

        chunk = chunk.sort_values("sale_date").reset_index(drop=True)

        uplifts: list[float] = []
        discounts: list[float] = []
        impacts: list[float] = []
        for _, row in chunk.iterrows():
            date_str = row["sale_date"]
            promo_key = (date_str, product_id, channel_id)
            if promo_key not in promo_cache:
                promo_cache[promo_key] = _promo_uplift(promos, date_str, product_id, channel_id)
            uplift, promo_discount = promo_cache[promo_key]
            uplifts.append(uplift)
            discounts.append(max(promo_discount, float(row["discount_pct"])))

            holiday_key = (date_str, region_id)
            if holiday_key not in holiday_cache:
                holiday_cache[holiday_key] = _holiday_impact(holidays, date_str, region_id)
            impacts.append(holiday_cache[holiday_key])

        frame = pd.DataFrame(
            {
                "ds": pd.to_datetime(chunk["sale_date"]),
                "y": chunk["y"].astype(float).to_numpy(),
                "promo_uplift": np.asarray(uplifts, dtype=float),
                "discount_pct": np.asarray(discounts, dtype=float),
                "unit_price": chunk["unit_price"].astype(float).to_numpy(),
                "holiday_impact": np.asarray(impacts, dtype=float),
            }
        )
        frames[str(key)] = frame

    return frames


def build_future_frame(
    last_date: str,
    horizon: int,
    promos: list[Promo],
    holidays: list[Holiday],
    product_id=None,
    region_id=None,
    channel_id=None,
    recent_discount: float = 0.0,
    recent_price: float = 0.0,
) -> pd.DataFrame:
    """Tạo khung regressor cho các ngày tương lai."""
    last_dt = pd.to_datetime(last_date)
    future_dates = [
        (last_dt + pd.Timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(1, horizon + 1)
    ]

    uplifts, discounts, impacts = [], [], []
    for date_str in future_dates:
        uplift, promo_discount = _promo_uplift(promos, date_str, product_id, channel_id)
        uplifts.append(uplift)
        discounts.append(promo_discount if promo_discount > 0 else recent_discount)
        impacts.append(_holiday_impact(holidays, date_str, region_id))

    return pd.DataFrame(
        {
            "ds": pd.to_datetime(pd.Series(future_dates)),
            "promo_uplift": np.asarray(uplifts, dtype=float),
            "discount_pct": np.asarray(discounts, dtype=float),
            "unit_price": np.full(len(future_dates), float(recent_price), dtype=float),
            "holiday_impact": np.asarray(impacts, dtype=float),
        }
    )


def _series_identity(key: str, granularity: str) -> dict:
    if granularity == "total":
        return {"product_id": None, "region_id": None, "channel_id": None}
    if granularity == "product":
        return {"product_id": int(key), "region_id": None, "channel_id": None}
    if granularity == "region":
        return {"product_id": None, "region_id": int(key), "channel_id": None}
    if granularity == "channel":
        return {"product_id": None, "region_id": None, "channel_id": int(key)}
    # product_region -> key dạng "(1, 2)" hoặc "1,2"
    parts = [int(part) for part in key.strip("() ").split(",")]
    return {"product_id": parts[0], "region_id": parts[1], "channel_id": None}


# ---------------------------------------------------------------------------
# Huấn luyện
# ---------------------------------------------------------------------------
def _total_frame(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    if "__total__" in frames:
        return frames["__total__"]
    combined = pd.concat(frames.values(), ignore_index=True)
    grouped = combined.groupby("ds", as_index=False).agg(
        y=("y", "sum"),
        promo_uplift=("promo_uplift", "max"),
        discount_pct=("discount_pct", "mean"),
        unit_price=("unit_price", "mean"),
        holiday_impact=("holiday_impact", "max"),
    )
    return grouped.sort_values("ds").reset_index(drop=True)


def run_training(
    db: Session,
    request,
    user_id: int | None = None,
    existing_run: ForecastRun | None = None,
) -> ForecastRun:
    """Chạy huấn luyện + dự báo và lưu vào DB (đồng bộ)."""
    scope = {
        "product_ids": request.product_ids,
        "region_ids": request.region_ids,
        "channel_ids": request.channel_ids,
    }
    models = list(request.models or [MODEL_SEASONAL_NAIVE])
    granularity = request.granularity
    horizon = request.horizon

    params = {
        "models": models,
        "backtest_folds": request.backtest_folds,
        "test_size": request.test_size,
    }

    if existing_run is not None:
        run = existing_run
        run.status = JOB_RUNNING
        run.model_name = models[0]
        run.horizon = horizon
        run.granularity = granularity
        run.scope = scope
        run.params = params
        run.error_message = None
        db.commit()
    else:
        run = ForecastRun(
            name=request.name or f"Forecast {datetime.now(timezone.utc):%Y-%m-%d %H:%M}",
            created_by=user_id,
            status=JOB_RUNNING,
            model_name=models[0],
            horizon=horizon,
            granularity=granularity,
            scope=scope,
            params=params,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

    try:
        raw = load_raw_sales(db, scope)
        if raw.empty:
            raise ValueError("Không có dữ liệu bán hàng trong phạm vi đã chọn. Hãy nạp dữ liệu trước.")

        promos = load_promos(db)
        holidays = load_holidays(db)
        frames = build_series_frames(raw, granularity, promos, holidays)
        if not frames:
            raise ValueError("Không tạo được chuỗi thời gian nào từ dữ liệu hiện có.")
        if len(frames) > MAX_SERIES:
            raise ValueError(
                f"Quá nhiều chuỗi ({len(frames)}). Hãy thu hẹp phạm vi hoặc chọn độ chi tiết thấp hơn."
            )

        total = _total_frame(frames)
        run.train_start = str(total["ds"].min().date())
        run.train_end = str(total["ds"].max().date())

        # --- 1. Backtest tất cả mô hình để xếp hạng ---
        leaderboard: list[dict] = []
        for model_name in models:
            if not is_available(model_name):
                leaderboard.append(
                    {
                        "model_name": model_name,
                        "label": MODEL_LABELS.get(model_name, model_name),
                        "mape": 0.0,
                        "smape": 0.0,
                        "rmse": 0.0,
                        "mae": 0.0,
                        "bias": 0.0,
                        "rank": 0,
                        "is_best": False,
                        "note": "Mô hình không khả dụng (thiếu thư viện)",
                        "skipped": True,
                    }
                )
                continue
            try:
                metrics = rolling_origin_backtest(
                    model_name,
                    total,
                    n_folds=request.backtest_folds,
                    test_size=request.test_size,
                )
                leaderboard.append(
                    {
                        "model_name": model_name,
                        "label": MODEL_LABELS.get(model_name, model_name),
                        "mape": metrics["mape"],
                        "smape": metrics["smape"],
                        "rmse": metrics["rmse"],
                        "mae": metrics["mae"],
                        "bias": metrics["bias"],
                        "coverage": metrics.get("coverage"),
                        "folds": metrics.get("folds", []),
                        "rank": 0,
                        "is_best": False,
                        "note": None,
                        "skipped": False,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                leaderboard.append(
                    {
                        "model_name": model_name,
                        "label": MODEL_LABELS.get(model_name, model_name),
                        "mape": 0.0,
                        "smape": 0.0,
                        "rmse": 0.0,
                        "mae": 0.0,
                        "bias": 0.0,
                        "rank": 0,
                        "is_best": False,
                        "note": f"Lỗi backtest: {exc}",
                        "skipped": True,
                    }
                )

        usable = [item for item in leaderboard if not item.get("skipped")]
        if not usable:
            raise ValueError(
                "Không mô hình nào huấn luyện được. Kiểm tra lại dữ liệu hoặc thư viện (prophet/scikit-learn)."
            )

        usable.sort(key=lambda item: ranking_score(item))
        for index, item in enumerate(usable, start=1):
            item["rank"] = index
        usable[0]["is_best"] = True
        best_model = usable[0]["model_name"]

        run.model_name = best_model
        run.leaderboard = leaderboard
        run.metrics = {
            key: usable[0].get(key)
            for key in ("mape", "smape", "rmse", "mae", "bias", "coverage")
        }
        run.metrics["accuracy"] = accuracy_from_mape(usable[0].get("mape"))
        run.metrics["best_model"] = best_model
        run.metrics["best_model_label"] = MODEL_LABELS.get(best_model, best_model)

        # --- 2. Huấn luyện mô hình tốt nhất trên từng chuỗi và dự báo ---
        forecast_rows: list[Forecast] = []
        for key, frame in frames.items():
            if len(frame) < 60:
                continue
            identity = _series_identity(key, granularity)
            recent_discount = float(frame["discount_pct"].tail(28).mean())
            recent_price = float(frame["unit_price"].tail(28).mean())
            future = build_future_frame(
                str(frame["ds"].max().date()),
                horizon,
                promos,
                holidays,
                identity["product_id"],
                identity["region_id"],
                identity["channel_id"],
                recent_discount,
                recent_price,
            )
            forecaster = build_forecaster(best_model)
            forecaster.fit(frame, future)
            output = forecaster.predict()

            for step, date_value in enumerate(future["ds"]):
                forecast_rows.append(
                    Forecast(
                        run_id=run.id,
                        forecast_date=str(pd.Timestamp(date_value).date()),
                        product_id=identity["product_id"],
                        region_id=identity["region_id"],
                        channel_id=identity["channel_id"],
                        model_name=best_model,
                        yhat=safe_round(output.yhat[step], 3),
                        yhat_lower=safe_round(output.lower[step], 3),
                        yhat_upper=safe_round(output.upper[step], 3),
                    )
                )

        if not forecast_rows:
            raise ValueError("Không tạo được điểm dự báo nào (mỗi chuỗi quá ngắn, cần >= 60 điểm).")

        db.bulk_save_objects(forecast_rows)

        # --- 3. Phân rã đóng góp (drivers) ---
        drivers = compute_drivers(total)
        drivers["horizon"] = horizon
        drivers["granularity"] = granularity
        drivers["n_series"] = len(frames)
        drivers["forecast_total_units"] = safe_round(
            float(np.sum([row.yhat for row in forecast_rows])), 2
        )
        run.drivers = drivers

        run.status = JOB_COMPLETED
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(ForecastRun, run.id)
        run.status = JOB_FAILED
        run.error_message = str(exc)[:1000]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run


# ---------------------------------------------------------------------------
# Truy vấn kết quả
# ---------------------------------------------------------------------------
def get_run_points(db: Session, run_id: int) -> list[Forecast]:
    return (
        db.query(Forecast)
        .filter(Forecast.run_id == run_id)
        .order_by(Forecast.forecast_date.asc())
        .all()
    )


def aggregate_points_by_date(points: list[Forecast]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for point in points:
        bucket = buckets.setdefault(
            point.forecast_date,
            {"forecast_date": point.forecast_date, "yhat": 0.0, "yhat_lower": 0.0, "yhat_upper": 0.0},
        )
        bucket["yhat"] += float(point.yhat)
        bucket["yhat_lower"] += float(point.yhat_lower)
        bucket["yhat_upper"] += float(point.yhat_upper)
    return [buckets[key] for key in sorted(buckets)]


def build_history(db: Session, scope: dict, last_n: int = 90) -> list[dict]:
    raw = load_raw_sales(db, scope)
    if raw.empty:
        return []
    grouped = raw.groupby("sale_date", as_index=False)["quantity"].sum().sort_values("sale_date")
    tail = grouped.tail(last_n)
    return [{"ds": row.sale_date, "y": safe_round(row.quantity, 2)} for row in tail.itertuples()]


def lookup_names(db: Session) -> dict:
    return {
        "products": {item.id: item.name for item in db.query(Product).all()},
        "regions": {item.id: item.name for item in db.query(Region).all()},
        "channels": {item.id: item.name for item in db.query(Channel).all()},
    }


# ---------------------------------------------------------------------------
# Chạy nền (background job)
# ---------------------------------------------------------------------------
@dataclass
class TrainParams:
    """Tham số huấn luyện đã được chuẩn hóa (dùng được cả trong background task)."""

    name: str | None = None
    models: list[str] = field(default_factory=lambda: [MODEL_SEASONAL_NAIVE])
    horizon: int = 30
    granularity: str = "total"
    product_ids: list[int] | None = None
    region_ids: list[int] | None = None
    channel_ids: list[int] | None = None
    backtest_folds: int = 3
    test_size: int = 28

    @classmethod
    def from_request(cls, request) -> "TrainParams":
        return cls(
            name=getattr(request, "name", None),
            models=list(getattr(request, "models", None) or [MODEL_SEASONAL_NAIVE]),
            horizon=int(getattr(request, "horizon", 30)),
            granularity=getattr(request, "granularity", "total"),
            product_ids=getattr(request, "product_ids", None),
            region_ids=getattr(request, "region_ids", None),
            channel_ids=getattr(request, "channel_ids", None),
            backtest_folds=int(getattr(request, "backtest_folds", 3)),
            test_size=int(getattr(request, "test_size", 28)),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "TrainParams":
        return cls(
            name=data.get("name"),
            models=list(data.get("models") or [MODEL_SEASONAL_NAIVE]),
            horizon=int(data.get("horizon", 30)),
            granularity=data.get("granularity", "total"),
            product_ids=data.get("product_ids"),
            region_ids=data.get("region_ids"),
            channel_ids=data.get("channel_ids"),
            backtest_folds=int(data.get("backtest_folds", 3)),
            test_size=int(data.get("test_size", 28)),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "models": self.models,
            "horizon": self.horizon,
            "granularity": self.granularity,
            "product_ids": self.product_ids,
            "region_ids": self.region_ids,
            "channel_ids": self.channel_ids,
            "backtest_folds": self.backtest_folds,
            "test_size": self.test_size,
        }


def create_pending_run(db: Session, params: TrainParams, user_id: int | None = None) -> ForecastRun:
    """Tạo bản ghi run ở trạng thái pending để chạy nền."""
    run = ForecastRun(
        name=params.name or f"Forecast {datetime.now(timezone.utc):%Y-%m-%d %H:%M}",
        created_by=user_id,
        status=JOB_PENDING,
        model_name=params.models[0] if params.models else MODEL_SEASONAL_NAIVE,
        horizon=params.horizon,
        granularity=params.granularity,
        scope={
            "product_ids": params.product_ids,
            "region_ids": params.region_ids,
            "channel_ids": params.channel_ids,
        },
        params={
            "models": params.models,
            "backtest_folds": params.backtest_folds,
            "test_size": params.test_size,
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_run(run_id: int, params_dict: dict) -> None:
    """Chạy huấn luyện trong một session riêng (dùng cho background task)."""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        run = db.get(ForecastRun, run_id)
        if run is None:
            return
        params = TrainParams.from_dict(params_dict)
        run_training(db, params, user_id=run.created_by, existing_run=run)
