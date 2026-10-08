"""Scenario planning: tạo và truy vấn kịch bản what-if."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.constants import JOB_FAILED
from app.core.deps import AnalystUser, DbSession, ViewerUser
from app.models import Scenario
from app.schemas.common import Message
from app.schemas.scenario import ScenarioCreate, ScenarioOut
from app.services.scenario import create_scenario, get_scenario_points

router = APIRouter(prefix="/scenario", tags=["Scenario planning"])


def _to_out(db: Session, scenario: Scenario) -> ScenarioOut:
    summary = scenario.summary or {}
    return ScenarioOut(
        id=scenario.id,
        base_run_id=scenario.base_run_id,
        name=scenario.name,
        status=scenario.status,
        assumptions=scenario.assumptions,
        summary=summary,
        error_message=scenario.error_message,
        created_at=scenario.created_at,
        points=get_scenario_points(db, scenario.id),
        inventory_plan=summary.get("inventory_plan", []),
    )


@router.post("", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED, summary="Tạo kịch bản mới")
def create(payload: ScenarioCreate, user: AnalystUser, db: DbSession) -> ScenarioOut:
    scenario = create_scenario(db, payload, user_id=user.id)
    if scenario.status == JOB_FAILED:
        raise HTTPException(status_code=400, detail=scenario.error_message or "Không tạo được kịch bản")
    return _to_out(db, scenario)


@router.get("", response_model=list[ScenarioOut], summary="Danh sách kịch bản")
def list_scenarios(
    user: ViewerUser,
    db: DbSession,
    base_run_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ScenarioOut]:
    query = db.query(Scenario)
    if base_run_id:
        query = query.filter(Scenario.base_run_id == base_run_id)
    rows = query.order_by(Scenario.created_at.desc()).limit(limit).all()
    return [_to_out(db, row) for row in rows]


@router.get("/{scenario_id}", response_model=ScenarioOut, summary="Chi tiết kịch bản")
def get_scenario(scenario_id: int, user: ViewerUser, db: DbSession) -> ScenarioOut:
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kịch bản")
    return _to_out(db, scenario)


@router.delete("/{scenario_id}", response_model=Message, summary="Xóa kịch bản")
def delete_scenario(scenario_id: int, user: AnalystUser, db: DbSession) -> Message:
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy kịch bản")
    db.delete(scenario)
    db.commit()
    return Message(message=f"Đã xóa kịch bản #{scenario_id}")
