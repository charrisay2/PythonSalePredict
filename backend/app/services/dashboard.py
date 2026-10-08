"""Service tổng hợp số liệu cho dashboard."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import JOB_COMPLETED
from app.core.utils import safe_round
from app.ml.metrics import accuracy_from_mape
from app.models import Alert, ForecastRun, Product, Sale


def build_summary(db: Session) -> dict:
    totals = db.query(
        func.sum(Sale.quantity).label("units"),
        func.sum(Sale.revenue).label("revenue"),
        func.min(Sale.sale_date).label("start"),
        func.max(Sale.sale_date).label("end"),
        func.count(Sale.id).label("rows"),
    ).one()

    total_units = float(totals.units or 0.0)
    total_revenue = float(totals.revenue or 0.0)
    active_products = db.query(func.count(Product.id)).filter(Product.is_active.is_(True)).scalar() or 0

    latest_run = (
        db.query(ForecastRun)
        .filter(ForecastRun.status == JOB_COMPLETED)
        .order_by(ForecastRun.created_at.desc())
        .first()
    )

    forecast_accuracy = None
    forecast_units = None
    if latest_run is not None:
        metrics = latest_run.metrics or {}
        forecast_accuracy = metrics.get("accuracy") or accuracy_from_mape(metrics.get("mape"))
        drivers = latest_run.drivers or {}
        forecast_units = drivers.get("forecast_total_units")

    open_alerts = db.query(func.count(Alert.id)).filter(Alert.status == "open").scalar() or 0

    top_products_rows = (
        db.query(Product.name, func.sum(Sale.quantity).label("units"), func.sum(Sale.revenue).label("revenue"))
        .join(Sale, Sale.product_id == Product.id)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(Sale.quantity).desc())
        .limit(8)
        .all()
    )
    top_products = [
        {"name": row.name, "units": safe_round(row.units or 0, 2), "revenue": safe_round(row.revenue or 0, 2)}
        for row in top_products_rows
    ]

    monthly_rows = (
        db.query(
            func.substr(Sale.sale_date, 1, 7).label("month"),
            func.sum(Sale.quantity).label("units"),
            func.sum(Sale.revenue).label("revenue"),
        )
        .group_by(func.substr(Sale.sale_date, 1, 7))
        .order_by(func.substr(Sale.sale_date, 1, 7))
        .all()
    )
    monthly_series = [
        {"month": row.month, "units": safe_round(row.units or 0, 2), "revenue": safe_round(row.revenue or 0, 2)}
        for row in monthly_rows
    ]

    recent_runs = [
        {
            "id": run.id,
            "name": run.name,
            "status": run.status,
            "model_name": run.model_name,
            "granularity": run.granularity,
            "horizon": run.horizon,
            "mape": (run.metrics or {}).get("mape"),
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
        for run in db.query(ForecastRun).order_by(ForecastRun.created_at.desc()).limit(6).all()
    ]

    kpis = [
        {
            "key": "revenue",
            "label": "Tổng doanh thu",
            "value": safe_round(total_revenue, 2),
            "unit": "VND",
            "hint": f"{int(totals.rows or 0)} bản ghi bán hàng",
        },
        {
            "key": "units",
            "label": "Tổng sản lượng",
            "value": safe_round(total_units, 2),
            "unit": "đơn vị",
            "hint": f"Từ {totals.start or '-'} đến {totals.end or '-'}",
        },
        {
            "key": "products",
            "label": "Sản phẩm đang hoạt động",
            "value": float(active_products),
            "unit": "SKU",
            "hint": "Danh mục sản phẩm",
        },
        {
            "key": "accuracy",
            "label": "Độ chính xác dự báo",
            "value": float(forecast_accuracy or 0.0),
            "unit": "%",
            "hint": "Từ lần dự báo gần nhất",
        },
        {
            "key": "forecast_units",
            "label": "Nhu cầu dự báo",
            "value": float(forecast_units or 0.0),
            "unit": "đơn vị",
            "hint": f"Tầm dự báo {latest_run.horizon if latest_run else 0} ngày",
        },
        {
            "key": "alerts",
            "label": "Cảnh báo đang mở",
            "value": float(open_alerts),
            "unit": "cảnh báo",
            "hint": "Rủi ro mất hàng / tồn kho cao",
        },
    ]

    return {
        "total_revenue": safe_round(total_revenue, 2),
        "total_units": safe_round(total_units, 2),
        "active_products": int(active_products),
        "date_start": totals.start,
        "date_end": totals.end,
        "latest_run_id": latest_run.id if latest_run else None,
        "forecast_accuracy": forecast_accuracy,
        "forecast_units": forecast_units,
        "open_alerts": int(open_alerts),
        "kpis": kpis,
        "top_products": top_products,
        "recent_runs": recent_runs,
        "monthly_series": monthly_series,
    }
