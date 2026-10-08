"""Dự báo: danh sách mô hình, huấn luyện, so sánh, truy vấn kết quả."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.core.constants import JOB_COMPLETED, MODEL_LABELS
from app.core.deps import AnalystUser, DbSession, ViewerUser
from app.ml.metrics import accuracy_from_mape
from app.ml.registry import available_models
from app.models import Forecast, ForecastRun
from app.schemas.common import Message
from app.schemas.forecast import (
    CompareRequest,
    CompareResponse,
    ForecastResponse,
    ForecastRunOut,
    LeaderboardEntry,
    TrainRequest,
)
from app.services.forecasting import (
    TrainParams,
    aggregate_points_by_date,
    build_history,
    create_pending_run,
    execute_run,
    get_run_points,
    run_training,
)

router = APIRouter(prefix="/forecast", tags=["Dự báo"])


def _get_run(db: DbSession, run_id: int) -> ForecastRun:
    run = db.get(ForecastRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần dự báo")
    return run


@router.get("/models", summary="Danh sách mô hình dự báo khả dụng")
def list_models(user: ViewerUser) -> list[dict]:
    return available_models()


@router.post(
    "/train",
    response_model=ForecastRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Huấn luyện và dự báo (mặc định chạy nền)",
)
def train(
    payload: TrainRequest,
    background: BackgroundTasks,
    user: AnalystUser,
    db: DbSession,
) -> ForecastRunOut:
    params = TrainParams.from_request(payload)

    if payload.wait:
        run = run_training(db, params, user_id=user.id)
        return ForecastRunOut.model_validate(run)

    run = create_pending_run(db, params, user_id=user.id)
    background.add_task(execute_run, run.id, params.to_dict())
    return ForecastRunOut.model_validate(run)


@router.post("/compare", response_model=CompareResponse, summary="So sánh nhiều mô hình (đồng bộ)")
def compare(payload: CompareRequest, user: AnalystUser, db: DbSession) -> CompareResponse:
    params = TrainParams(
        name="So sánh mô hình",
        models=list(payload.models or []),
        horizon=payload.horizon,
        granularity=payload.granularity,
        product_ids=payload.product_ids,
        region_ids=payload.region_ids,
        channel_ids=payload.channel_ids,
        backtest_folds=payload.backtest_folds,
        test_size=payload.test_size,
    )
    run = run_training(db, params, user_id=user.id)
    leaderboard = [
        LeaderboardEntry(
            model_name=item.get("model_name", ""),
            label=item.get("label") or MODEL_LABELS.get(item.get("model_name", ""), ""),
            mape=float(item.get("mape") or 0.0),
            smape=float(item.get("smape") or 0.0),
            rmse=float(item.get("rmse") or 0.0),
            mae=float(item.get("mae") or 0.0),
            bias=float(item.get("bias") or 0.0),
            rank=int(item.get("rank") or 0),
            is_best=bool(item.get("is_best")),
            note=item.get("note"),
        )
        for item in (run.leaderboard or [])
    ]
    return CompareResponse(run=ForecastRunOut.model_validate(run), leaderboard=leaderboard)


@router.get("/runs", response_model=list[ForecastRunOut], summary="Lịch sử các lần dự báo")
def list_runs(
    user: ViewerUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ForecastRunOut]:
    runs = db.query(ForecastRun).order_by(ForecastRun.created_at.desc()).limit(limit).all()
    return [ForecastRunOut.model_validate(run) for run in runs]


@router.get("/runs/{run_id}", response_model=ForecastRunOut, summary="Thông tin một lần dự báo")
def get_run(run_id: int, user: ViewerUser, db: DbSession) -> ForecastRunOut:
    return ForecastRunOut.model_validate(_get_run(db, run_id))


@router.get("/runs/{run_id}/result", response_model=ForecastResponse, summary="Kết quả dự báo chi tiết")
def get_run_result(
    run_id: int,
    user: ViewerUser,
    db: DbSession,
    history_days: int = Query(default=90, ge=7, le=730),
    granularity_filter: str = Query(default="total", description="total | product | region | channel"),
    product_id: int | None = None,
    region_id: int | None = None,
) -> ForecastResponse:
    run = _get_run(db, run_id)

    query = db.query(Forecast).filter(Forecast.run_id == run_id)
    if product_id is not None:
        query = query.filter(Forecast.product_id == product_id)
    if region_id is not None:
        query = query.filter(Forecast.region_id == region_id)
    points = query.order_by(Forecast.forecast_date.asc()).all()

    aggregated = aggregate_points_by_date(points)
    total_units = sum(float(item["yhat"]) for item in aggregated)

    history = build_history(db, run.scope or {}, last_n=history_days) if run.scope is not None else []

    return ForecastResponse(
        run=ForecastRunOut.model_validate(run),
        points=aggregated,
        history=history,
        total_forecast_units=round(total_units, 2),
    )


@router.get("/runs/{run_id}/leaderboard", summary="Bảng xếp hạng mô hình của một lần dự báo")
def get_leaderboard(run_id: int, user: ViewerUser, db: DbSession) -> dict:
    run = _get_run(db, run_id)
    return {
        "run_id": run.id,
        "best_model": run.model_name,
        "metrics": run.metrics or {},
        "accuracy": (run.metrics or {}).get("accuracy") or accuracy_from_mape((run.metrics or {}).get("mape")),
        "leaderboard": run.leaderboard or [],
        "drivers": run.drivers or {},
    }


@router.delete("/runs/{run_id}", response_model=Message, summary="Xóa một lần dự báo")
def delete_run(run_id: int, user: AnalystUser, db: DbSession) -> Message:
    run = _get_run(db, run_id)
    db.query(Forecast).filter(Forecast.run_id == run_id).delete()
    db.delete(run)
    db.commit()
    return Message(message=f"Đã xóa lần dự báo #{run_id}")


@router.get("/latest", response_model=ForecastRunOut | None, summary="Lần dự báo hoàn thành gần nhất")
def latest_run(user: ViewerUser, db: DbSession) -> ForecastRunOut | None:
    run = (
        db.query(ForecastRun)
        .filter(ForecastRun.status == JOB_COMPLETED)
        .order_by(ForecastRun.created_at.desc())
        .first()
    )
    if run is None:
        return None
    return ForecastRunOut.model_validate(run)
