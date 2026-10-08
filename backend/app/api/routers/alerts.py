"""Cảnh báo rủi ro mất hàng / tồn kho cao."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import AnalystUser, DbSession, ViewerUser
from app.models import Alert, ForecastRun, Product, Region
from app.schemas.alert import AlertWithNames
from app.schemas.common import Message
from app.services.inventory import compute_inventory_plan, recompute_alerts

router = APIRouter(prefix="/alerts", tags=["Cảnh báo"])


def _decorate(db: DbSession, alerts: list[Alert]) -> list[AlertWithNames]:
    products = {item.id: item.name for item in db.query(Product).all()}
    regions = {item.id: item.name for item in db.query(Region).all()}
    result = []
    for alert in alerts:
        payload = AlertWithNames.model_validate(alert)
        payload.product_name = products.get(alert.product_id) if alert.product_id else None
        payload.region_name = regions.get(alert.region_id) if alert.region_id else None
        result.append(payload)
    return result


@router.get("", response_model=list[AlertWithNames], summary="Danh sách cảnh báo")
def list_alerts(
    user: ViewerUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    alert_type: str | None = Query(default=None),
    run_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AlertWithNames]:
    query = db.query(Alert)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if run_id:
        query = query.filter(Alert.run_id == run_id)
    alerts = query.order_by(Alert.risk_score.desc(), Alert.created_at.desc()).limit(limit).all()
    return _decorate(db, alerts)


@router.post("/recompute", response_model=list[AlertWithNames], summary="Tính lại cảnh báo từ một lần dự báo")
def recompute(
    user: AnalystUser,
    db: DbSession,
    run_id: int | None = Query(default=None, description="Mặc định dùng lần dự báo hoàn thành mới nhất"),
) -> list[AlertWithNames]:
    if run_id is None:
        latest = (
            db.query(ForecastRun)
            .filter(ForecastRun.status == "completed")
            .order_by(ForecastRun.created_at.desc())
            .first()
        )
        if latest is None:
            raise HTTPException(status_code=404, detail="Chưa có lần dự báo nào hoàn thành")
        run_id = latest.id

    plan = compute_inventory_plan(db, run_id)
    if not plan:
        raise HTTPException(status_code=400, detail="Lần dự báo này chưa có dữ liệu để tính cảnh báo")
    alerts = recompute_alerts(db, run_id, plan)
    return _decorate(db, alerts)


@router.patch("/{alert_id}/ack", response_model=AlertWithNames, summary="Đánh dấu đã xử lý cảnh báo")
def acknowledge(alert_id: int, user: AnalystUser, db: DbSession) -> AlertWithNames:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    alert.status = "ack"
    db.commit()
    db.refresh(alert)
    return _decorate(db, [alert])[0]
