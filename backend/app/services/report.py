"""Xuất báo cáo: Excel (.xlsx), PDF và CSV."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.core.constants import MODEL_LABELS
from app.core.fonts import ensure_unicode_font
from app.core.utils import safe_round
from app.models import Alert, Forecast, ForecastRun, Product, Region, Scenario
from app.services.forecasting import aggregate_points_by_date
from app.services.inventory import compute_inventory_plan


def _run_frame(db: Session, run: ForecastRun) -> pd.DataFrame:
    points = db.query(Forecast).filter(Forecast.run_id == run.id).all()
    products = {item.id: item.name for item in db.query(Product).all()}
    regions = {item.id: item.name for item in db.query(Region).all()}
    rows = [
        {
            "Ngày": point.forecast_date,
            "Sản phẩm": products.get(point.product_id, "Tất cả") if point.product_id else "Tất cả",
            "Khu vực": regions.get(point.region_id, "Tất cả") if point.region_id else "Tất cả",
            "Dự báo": safe_round(point.yhat, 2),
            "Cận dưới": safe_round(point.yhat_lower, 2),
            "Cận trên": safe_round(point.yhat_upper, 2),
            "Mô hình": point.model_name,
        }
        for point in points
    ]
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("Ngày").reset_index(drop=True)
    return frame


def _summary_frame(run: ForecastRun) -> pd.DataFrame:
    metrics = run.metrics or {}
    drivers = run.drivers or {}
    rows = [
        ("Tên lần dự báo", run.name),
        ("Trạng thái", run.status),
        ("Mô hình tốt nhất", MODEL_LABELS.get(run.model_name, run.model_name)),
        ("Độ chi tiết", run.granularity),
        ("Tầm dự báo (ngày)", run.horizon),
        ("Dữ liệu từ", run.train_start or "-"),
        ("Dữ liệu đến", run.train_end or "-"),
        ("MAPE (%)", metrics.get("mape")),
        ("sMAPE (%)", metrics.get("smape")),
        ("RMSE", metrics.get("rmse")),
        ("MAE", metrics.get("mae")),
        ("Bias", metrics.get("bias")),
        ("Độ chính xác ước tính (%)", metrics.get("accuracy")),
        ("Tổng nhu cầu dự báo (đơn vị)", drivers.get("forecast_total_units")),
        ("Biên độ theo tuần (đơn vị)", drivers.get("weekly_amplitude_units")),
        ("Tác động ngày lễ (đơn vị)", drivers.get("holiday_lift_units")),
        ("Tác động khuyến mãi (đơn vị)", drivers.get("promo_lift_units")),
        ("Xuất báo cáo lúc", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
    ]
    return pd.DataFrame(rows, columns=["Chỉ tiêu", "Giá trị"])


def _leaderboard_frame(run: ForecastRun) -> pd.DataFrame:
    leaderboard = run.leaderboard or []
    rows = [
        {
            "Hạng": item.get("rank"),
            "Mô hình": item.get("label") or MODEL_LABELS.get(item.get("model_name"), item.get("model_name")),
            "MAPE (%)": item.get("mape"),
            "sMAPE (%)": item.get("smape"),
            "RMSE": item.get("rmse"),
            "MAE": item.get("mae"),
            "Bias": item.get("bias"),
            "Tốt nhất": "Có" if item.get("is_best") else "",
            "Ghi chú": item.get("note") or "",
        }
        for item in leaderboard
    ]
    frame = pd.DataFrame(rows)
    if not frame.empty and "Hạng" in frame.columns:
        # Bảng xếp hạng lưu theo thứ tự chạy backtest, không phải theo hạng -> sắp lại cho dễ đọc.
        frame = frame.sort_values("Hạng", na_position="last").reset_index(drop=True)
    return frame


def _alerts_frame(db: Session, run_id: int) -> pd.DataFrame:
    products = {item.id: item.name for item in db.query(Product).all()}
    regions = {item.id: item.name for item in db.query(Region).all()}
    alerts = db.query(Alert).filter(Alert.run_id == run_id).all()
    rows = [
        {
            "Loại": "Mất hàng" if alert.alert_type == "stockout" else "Tồn kho cao",
            "Mức độ": alert.severity,
            "Sản phẩm": products.get(alert.product_id, "Tất cả") if alert.product_id else "Tất cả",
            "Khu vực": regions.get(alert.region_id, "Tất cả") if alert.region_id else "Tất cả",
            "Điểm rủi ro": safe_round(alert.risk_score, 2),
            "Khuyến nghị": alert.message,
            "Trạng thái": alert.status,
        }
        for alert in alerts
    ]
    return pd.DataFrame(rows)


def _inventory_frame(db: Session, run_id: int) -> pd.DataFrame:
    plan = compute_inventory_plan(db, run_id)
    return pd.DataFrame(plan) if plan else pd.DataFrame()


def export_csv(db: Session, run: ForecastRun) -> bytes:
    frame = _run_frame(db, run)
    return frame.to_csv(index=False).encode("utf-8-sig")


def export_excel(db: Session, run: ForecastRun) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _summary_frame(run).to_excel(writer, sheet_name="Tổng quan", index=False)
        _leaderboard_frame(run).to_excel(writer, sheet_name="So sánh mô hình", index=False)
        _run_frame(db, run).to_excel(writer, sheet_name="Chi tiết dự báo", index=False)
        alerts = _alerts_frame(db, run.id)
        if not alerts.empty:
            alerts.to_excel(writer, sheet_name="Cảnh báo", index=False)
        inventory = _inventory_frame(db, run.id)
        if not inventory.empty:
            inventory.to_excel(writer, sheet_name="Kế hoạch tồn kho", index=False)
    return buffer.getvalue()


def export_pdf(db: Session, run: ForecastRun) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Font mặc định Helvetica không có glyph tiếng Việt có dấu -> phải đăng ký font Unicode.
    unicode_fonts = ensure_unicode_font()
    base_font, bold_font = unicode_fonts or ("Helvetica", "Helvetica-Bold")

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=f"Báo cáo dự báo - {run.name}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleVi", parent=styles["Title"], fontSize=16, spaceAfter=12, fontName=bold_font
    )
    heading_style = ParagraphStyle(
        "HeadingVi", parent=styles["Heading2"], fontSize=12, spaceBefore=12, fontName=bold_font
    )
    body_style = ParagraphStyle(
        "BodyVi", parent=styles["BodyText"], fontSize=9.5, leading=13, fontName=base_font
    )

    story = [Paragraph(f"Báo cáo dự báo nhu cầu: {run.name}", title_style)]

    metrics = run.metrics or {}
    drivers = run.drivers or {}
    story.append(
        Paragraph(
            f"Mô hình tốt nhất: <b>{MODEL_LABELS.get(run.model_name, run.model_name)}</b> | "
            f"MAPE: <b>{metrics.get('mape')}%</b> | RMSE: <b>{metrics.get('rmse')}</b> | "
            f"Độ chính xác ước tính: <b>{metrics.get('accuracy')}%</b>",
            body_style,
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"Dữ liệu huấn luyện: {run.train_start} đến {run.train_end} | "
            f"Tầm dự báo: {run.horizon} ngày | Độ chi tiết: {run.granularity}",
            body_style,
        )
    )

    story.append(Paragraph("Bảng xếp hạng mô hình", heading_style))
    leaderboard = run.leaderboard or []
    table_data = [["Hạng", "Mô hình", "MAPE (%)", "sMAPE (%)", "RMSE", "MAE"]]
    for item in leaderboard:
        table_data.append(
            [
                str(item.get("rank", "")),
                item.get("label") or item.get("model_name", ""),
                str(item.get("mape", "")),
                str(item.get("smape", "")),
                str(item.get("rmse", "")),
                str(item.get("mae", "")),
            ]
        )
    table = Table(table_data, colWidths=[1.4 * cm, 6.2 * cm, 2.2 * cm, 2.4 * cm, 2.2 * cm, 2.2 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b73")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), base_font),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa5b1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)

    story.append(Paragraph("Yếu tố tác động nhu cầu", heading_style))
    story.append(
        Paragraph(
            f"- Xu hướng gần đây: <b>{drivers.get('trend_delta_units')}</b> đơn vị "
            f"({drivers.get('trend_delta_pct')}%)<br/>"
            f"- Biến động theo thứ trong tuần: <b>{drivers.get('weekly_amplitude_units')}</b> đơn vị "
            f"({drivers.get('weekly_amplitude_pct')}%)<br/>"
            f"- Tác động ngày lễ: <b>{drivers.get('holiday_lift_units')}</b> đơn vị<br/>"
            f"- Tác động khuyến mãi: <b>{drivers.get('promo_lift_units')}</b> đơn vị<br/>"
            f"- Tổng nhu cầu dự báo: <b>{drivers.get('forecast_total_units')}</b> đơn vị",
            body_style,
        )
    )

    alerts = _alerts_frame(db, run.id)
    story.append(Paragraph("Cảnh báo rủi ro mất hàng", heading_style))
    if alerts.empty:
        story.append(Paragraph("Không có cảnh báo rủi ro nào.", body_style))
    else:
        alert_data = [["Loại", "Mức độ", "Điểm rủi ro", "Khuyến nghị"]]
        for row in alerts.head(15).itertuples(index=False):
            alert_data.append([row[0], row[1], str(row[4]), str(row[5])[:110]])
        alert_table = Table(alert_data, colWidths=[2.6 * cm, 1.8 * cm, 2.2 * cm, 10 * cm])
        alert_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8a1f1f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), base_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa5b1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(alert_table)

    document.build(story)
    return buffer.getvalue()


def scenario_frame(db: Session, scenario: Scenario) -> pd.DataFrame:
    summary = scenario.summary or {}
    rows = [
        ("Tên kịch bản", scenario.name),
        ("Trạng thái", scenario.status),
        ("Tổng nhu cầu cơ sở (đơn vị)", summary.get("baseline_total_units")),
        ("Tổng nhu cầu kịch bản (đơn vị)", summary.get("scenario_total_units")),
        ("Chênh lệch (đơn vị)", summary.get("delta_units")),
        ("Chênh lệch (%)", summary.get("delta_pct")),
        ("Ngày cao điểm", summary.get("peak_date")),
        ("Số hàng rủi ro cao", summary.get("high_risk_items")),
    ]
    return pd.DataFrame(rows, columns=["Chỉ tiêu", "Giá trị"])
