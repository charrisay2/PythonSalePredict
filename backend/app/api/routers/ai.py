"""AI giải thích kết quả dự báo (có ràng buộc số liệu)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.ai.explainer import build_context, explain_run
from app.ai.providers import provider_status
from app.core.constants import JOB_COMPLETED
from app.core.deps import DbSession, ViewerUser
from app.models import ForecastRun
from app.schemas.ai import ExplainRequest, ExplanationOut

router = APIRouter(prefix="/ai", tags=["AI giải thích"])


@router.get("/status", summary="Trạng thái cấu hình LLM")
def status(user: ViewerUser) -> dict:
    return provider_status()


@router.post("/explain", response_model=ExplanationOut, summary="Giải thích kết quả dự báo")
def explain(payload: ExplainRequest, user: ViewerUser, db: DbSession) -> ExplanationOut:
    run = db.get(ForecastRun, payload.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần dự báo")
    if run.status != JOB_COMPLETED:
        raise HTTPException(status_code=400, detail="Lần dự báo chưa hoàn thành")
    try:
        result = explain_run(db, payload, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExplanationOut(**result)


@router.get("/context/{run_id}", summary="Ngữ cảnh số liệu mà AI được phép sử dụng")
def get_context(run_id: int, user: ViewerUser, db: DbSession) -> dict:
    run = db.get(ForecastRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần dự báo")
    return build_context(db, run)
