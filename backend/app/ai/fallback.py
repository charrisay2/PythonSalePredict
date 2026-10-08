"""Sinh giải thích bằng rule-based (không cần LLM) - vẫn đảm bảo dựa trên số liệu."""

from __future__ import annotations

from app.core.utils import safe_round
from app.ml.decomposition import dow_label


def _confidence_from_mape(mape: float | None) -> str:
    if mape is None:
        return "low"
    if mape <= 12:
        return "high"
    if mape <= 25:
        return "medium"
    return "low"


def build_fallback_explanation(context: dict) -> dict:
    run = context.get("run", {})
    metrics = context.get("metrics", {})
    drivers = context.get("drivers", {})
    summary_data = context.get("forecast_summary", {})
    risks = context.get("top_inventory_risks", [])
    overstocks = context.get("overstock_items", [])
    promos = context.get("upcoming_promos", [])
    holidays = context.get("upcoming_holidays", [])

    horizon = run.get("horizon", 0)
    model_label = run.get("model_label", "mô hình")
    total_units = summary_data.get("total_units", 0.0)
    avg_daily = summary_data.get("avg_daily", 0.0)
    peak_date = summary_data.get("peak_date")
    peak_units = summary_data.get("peak_units", 0.0)
    trend_pct = summary_data.get("trend_pct", 0.0)
    mape = metrics.get("mape")

    trend_word = "tăng" if trend_pct > 1 else ("giảm" if trend_pct < -1 else "đi ngang")

    summary_lines = [
        f"Mô hình {model_label} dự báo tổng nhu cầu {total_units:,.0f} đơn vị trong {horizon} ngày tới, "
        f"trung bình {avg_daily:,.1f} đơn vị/ngày."
    ]
    if peak_date:
        summary_lines.append(
            f"Ngày cao điểm dự kiến là {peak_date} với {peak_units:,.1f} đơn vị."
        )
    summary_lines.append(
        f"Nhu cầu nửa sau của kỳ dự báo {trend_word} {abs(trend_pct):.1f}% so với nửa đầu."
    )
    if mape is not None:
        summary_lines.append(
            f"Chất lượng mô hình: MAPE {mape}% (độ chính xác ước tính {metrics.get('accuracy')}%)."
        )
    if risks:
        worst = risks[0]
        summary_lines.append(
            f"Điểm cảnh báo lớn nhất: {worst.get('product_name')} tại {worst.get('region_name')} "
            f"có rủi ro mất hàng {worst.get('stockout_risk')}%."
        )

    reasons: list[dict] = []

    trend_units = drivers.get("trend_delta_units", 0.0)
    trend_delta_pct = drivers.get("trend_delta_pct", 0.0)
    reasons.append(
        {
            "factor": "Xu hướng gần đây",
            "direction": "up" if trend_units > 0 else ("down" if trend_units < 0 else "flat"),
            "magnitude_pct": safe_round(abs(trend_delta_pct), 2),
            "evidence": (
                f"Trung bình 28 ngày gần nhất chênh lệch {trend_units:,.1f} đơn vị "
                f"({trend_delta_pct}%) so với giai đoạn trước đó."
            ),
        }
    )

    reasons.append(
        {
            "factor": "Mùa vụ theo thứ trong tuần",
            "direction": "flat",
            "magnitude_pct": safe_round(drivers.get("weekly_amplitude_pct", 0.0), 2),
            "evidence": (
                f"Biên độ nhu cầu theo thứ là {drivers.get('weekly_amplitude_units', 0):,.1f} đơn vị "
                f"({drivers.get('weekly_amplitude_pct', 0)}%), cao nhất vào "
                f"{dow_label(int(drivers.get('best_dayofweek', 0)))}."
            ),
        }
    )

    holiday_lift = drivers.get("holiday_lift_units", 0.0)
    if abs(holiday_lift) > 0:
        reasons.append(
            {
                "factor": "Ngày lễ / sự kiện",
                "direction": "up" if holiday_lift > 0 else "down",
                "magnitude_pct": safe_round(abs(drivers.get("holiday_lift_pct", 0.0)), 2),
                "evidence": (
                    f"Trung bình ngày lễ cao hơn ngày thường {holiday_lift:,.1f} đơn vị "
                    f"({drivers.get('holiday_lift_pct', 0)}%)."
                ),
            }
        )

    promo_lift = drivers.get("promo_lift_units", 0.0)
    if abs(promo_lift) > 0:
        reasons.append(
            {
                "factor": "Chương trình khuyến mãi",
                "direction": "up" if promo_lift > 0 else "down",
                "magnitude_pct": safe_round(abs(drivers.get("promo_lift_pct", 0.0)), 2),
                "evidence": (
                    f"Ngày có khuyến mãi cao hơn ngày thường {promo_lift:,.1f} đơn vị "
                    f"({drivers.get('promo_lift_pct', 0)}%)."
                ),
            }
        )

    if mape is not None:
        reasons.append(
            {
                "factor": "Độ tin cậy của dự báo",
                "direction": "flat",
                "magnitude_pct": safe_round(float(mape), 2),
                "evidence": (
                    f"Sai số bình quân MAPE {mape}%, RMSE {metrics.get('rmse')}, "
                    f"Bias {metrics.get('bias')} trên dữ liệu kiểm định."
                ),
            }
        )

    actions: list[dict] = []

    for item in risks[:3]:
        risk = float(item.get("stockout_risk", 0.0))
        actions.append(
            {
                "action": (
                    f"Đặt bổ sung {item.get('suggested_order_qty', 0):,.0f} đơn vị cho "
                    f"{item.get('product_name')} tại {item.get('region_name')}"
                ),
                "rationale": (
                    f"Rủi ro mất hàng {risk:.0f}%: nhu cầu trong {item.get('lead_time_days')} ngày "
                    f"thời gian chờ là {item.get('lead_time_demand', 0):,.1f} đơn vị trong khi khả dụng "
                    f"{item.get('on_hand_qty', 0):,.1f} đơn vị. Điểm đặt hàng lại "
                    f"{item.get('reorder_point', 0):,.1f}."
                ),
                "priority": "high" if risk >= 70 else "medium",
                "owner": "Bộ phận cung ứng",
            }
        )

    for item in overstocks[:2]:
        actions.append(
            {
                "action": (
                    f"Chạy khuyến mãi giải phóng tồn cho {item.get('product_name')} tại "
                    f"{item.get('region_name')}"
                ),
                "rationale": (
                    f"Tồn kho {item.get('on_hand_qty', 0):,.1f} đơn vị cao hơn nhu cầu dự báo "
                    f"{item.get('forecast_units', 0):,.1f} đơn vị ({item.get('overstock_risk')}%)."
                ),
                "priority": "medium",
                "owner": "Bộ phận bán hàng",
            }
        )

    for promo in promos[:2]:
        actions.append(
            {
                "action": f"Chuẩn bị tồn kho cho chương trình khuyến mãi '{promo.get('name')}'",
                "rationale": (
                    f"Chương trình diễn ra từ {promo.get('start_date')} đến {promo.get('end_date')} "
                    f"với mức giảm {promo.get('discount_pct')}%, hệ số nhu cầu "
                    f"{promo.get('uplift_factor')}."
                ),
                "priority": "medium",
                "owner": "Bộ phận cung ứng",
            }
        )

    for holiday in holidays[:2]:
        actions.append(
            {
                "action": f"Tăng tồn kho trước {holiday.get('name')} ({holiday.get('holiday_date')})",
                "rationale": (
                    f"Dữ liệu lịch sử cho thấy ngày lễ này có hệ số nhu cầu "
                    f"{holiday.get('impact_factor')}."
                ),
                "priority": "medium" if float(holiday.get("impact_factor", 1.0)) >= 1.2 else "low",
                "owner": "Bộ phận cung ứng",
            }
        )

    actions.append(
        {
            "action": "Theo dõi lại sai số mô hình sau khi có dữ liệu thực tế",
            "rationale": (
                f"Sai số hiện tại MAPE {mape}%. Nên huấn luyện lại khi có thêm dữ liệu mới "
                f"để duy trì độ chính xác."
            ),
            "priority": "low",
            "owner": "Nhóm phân tích dữ liệu",
        }
    )

    return {
        "summary": " ".join(summary_lines),
        "reasons": reasons,
        "recommended_actions": actions,
        "confidence": _confidence_from_mape(mape),
    }
