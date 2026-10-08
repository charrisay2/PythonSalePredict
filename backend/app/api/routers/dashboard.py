"""Dashboard tổng quan."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import DbSession, ViewerUser
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import build_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummary, summary="Số liệu tổng quan cho dashboard")
def summary(user: ViewerUser, db: DbSession) -> DashboardSummary:
    return DashboardSummary(**build_summary(db))
