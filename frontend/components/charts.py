"""Các biểu đồ Plotly dùng chung."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

FORECAST_COLOR = "#4F46E5"
ACTUAL_COLOR = "#8891A8"
BAND_COLOR = "rgba(79, 70, 229, 0.16)"
SCENARIO_COLOR = "#0E9F6E"
RISK_COLORS = ["#2E9E5B", "#C99A16", "#C0392B"]

BASE_LAYOUT = dict(
    template="plotly_white",
    # t=70 để đủ chỗ cho 2 dải phía trên: dải 1 = tiêu đề, dải 2 = chú giải.
    margin=dict(l=10, r=10, t=70, b=10),
    height=380,
    hovermode="x unified",
    font=dict(family="sans-serif", size=12),
)


def _apply(figure: go.Figure, title: str, height: int | None = None, show_legend: bool = True) -> go.Figure:
    """Áp layout chung cho mọi biểu đồ.

    Sửa lỗi chồng chữ: trước đây tiêu đề (Plotly tự đặt sát mép trên) và chú giải
    (legend.y=1.02 - ngay trên vùng vẽ) rơi vào CÙNG một dải nên đè lên nhau.
    Bây giờ tách thành 2 dải riêng:
      - Tiêu đề ghim sát mép trên khung hình: yref="container", y=1, yanchor="top".
      - Chú giải nằm ngay trên vùng vẽ: y=1, yanchor="bottom".
    Khoảng trống được bao bởi margin top = 70px nên không bao giờ đè nhau.
    """
    layout = dict(BASE_LAYOUT)
    layout["title"] = dict(
        text=title,
        font=dict(size=15),
        x=0,
        xanchor="left",
        y=1.0,
        yanchor="top",
        yref="container",
    )
    layout["showlegend"] = show_legend
    layout["legend"] = dict(
        orientation="h",
        yanchor="bottom",
        y=1.0,
        xanchor="left",
        x=0,
    )
    if height:
        layout["height"] = height
    figure.update_layout(**layout)
    return figure


def _axis_range(values: pd.Series, pad: float = 0.18) -> list[float]:
    """Chừa khoảng trống phía trên để nhãn số (textposition="outside") không bị cắt."""
    top = float(values.max()) if len(values) else 0.0
    if top <= 0:
        return [0, 1]
    return [0, top * (1 + pad)]


def forecast_figure(history: list[dict], points: list[dict], title: str = "Nhu cầu thực tế và dự báo") -> go.Figure:
    figure = go.Figure()

    if history:
        hist = pd.DataFrame(history)
        figure.add_trace(
            go.Scatter(
                x=hist["ds"],
                y=hist["y"],
                name="Thực tế",
                mode="lines",
                line=dict(color=ACTUAL_COLOR, width=2),
            )
        )

    if points:
        frame = pd.DataFrame(points)
        figure.add_trace(
            go.Scatter(
                x=frame["forecast_date"],
                y=frame["yhat_upper"],
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=frame["forecast_date"],
                y=frame["yhat_lower"],
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor=BAND_COLOR,
                name="Khoảng tin cậy 95%",
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=frame["forecast_date"],
                y=frame["yhat"],
                name="Dự báo",
                mode="lines+markers",
                line=dict(color=FORECAST_COLOR, width=2.4),
                marker=dict(size=5),
            )
        )

    return _apply(figure, title)


def leaderboard_figure(leaderboard: list[dict]) -> go.Figure:
    usable = [item for item in leaderboard if not item.get("skipped")]
    if not usable:
        return _apply(go.Figure(), "So sánh sai số mô hình", show_legend=False)

    frame = pd.DataFrame(usable).sort_values("mape")
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=frame["label"],
            y=frame["mape"],
            name="MAPE (%)",
            marker_color=FORECAST_COLOR,
            text=[f"{value:.2f}%" for value in frame["mape"]],
            textposition="outside",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame["label"],
            y=frame["rmse"],
            name="RMSE",
            mode="markers+lines",
            marker=dict(color="#C99A16", size=9),
            line=dict(color="#C99A16", dash="dot"),
            yaxis="y2",
        )
    )
    figure.update_layout(
        yaxis=dict(title="MAPE (%)", range=_axis_range(frame["mape"])),
        yaxis2=dict(
            title="RMSE",
            overlaying="y",
            side="right",
            showgrid=False,
            range=_axis_range(frame["rmse"]),
        ),
    )
    return _apply(figure, "So sánh sai số giữa các mô hình", height=420)


def scenario_figure(points: list[dict], name: str = "Kịch bản") -> go.Figure:
    figure = go.Figure()
    if points:
        frame = pd.DataFrame(points)
        figure.add_trace(
            go.Scatter(
                x=frame["forecast_date"],
                y=frame["baseline_yhat"],
                name="Cơ sở",
                mode="lines",
                line=dict(color=ACTUAL_COLOR, width=2, dash="dash"),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=frame["forecast_date"],
                y=frame["scenario_yhat"],
                name=name,
                mode="lines",
                line=dict(color=SCENARIO_COLOR, width=2.4),
                fill="tonexty",
                fillcolor="rgba(14, 159, 110, 0.12)",
            )
        )
    return _apply(figure, "So sánh kịch bản cơ sở và kịch bản giả định")


def monthly_series_figure(series: list[dict]) -> go.Figure:
    figure = go.Figure()
    if series:
        frame = pd.DataFrame(series)
        figure.add_trace(
            go.Bar(
                x=frame["month"],
                y=frame["units"],
                name="Sản lượng",
                marker_color="#B9C0F0",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=frame["month"],
                y=frame["revenue"],
                name="Doanh thu",
                mode="lines+markers",
                line=dict(color=FORECAST_COLOR, width=2.4),
                yaxis="y2",
            )
        )
    figure.update_layout(
        yaxis=dict(title="Sản lượng (đơn vị)"),
        yaxis2=dict(title="Doanh thu (VND)", overlaying="y", side="right", showgrid=False),
    )
    return _apply(figure, "Sản lượng và doanh thu theo tháng", height=400)


def top_products_figure(products: list[dict]) -> go.Figure:
    figure = go.Figure()
    if products:
        frame = pd.DataFrame(products).sort_values("units")
        figure.add_trace(
            go.Bar(
                x=frame["units"],
                y=frame["name"],
                orientation="h",
                marker_color=FORECAST_COLOR,
                text=[f"{value:,.0f}" for value in frame["units"]],
                textposition="outside",
            )
        )
    return _apply(figure, "Top sản phẩm theo sản lượng", height=400, show_legend=False)


def drivers_figure(drivers: dict) -> go.Figure:
    labels = ["Xu hướng", "Mùa vụ tuần", "Ngày lễ", "Khuyến mãi"]
    values = [
        drivers.get("trend_delta_units") or 0.0,
        drivers.get("weekly_amplitude_units") or 0.0,
        drivers.get("holiday_lift_units") or 0.0,
        drivers.get("promo_lift_units") or 0.0,
    ]
    colors = [FORECAST_COLOR if value >= 0 else "#C0392B" for value in values]
    figure = go.Figure(
        go.Bar(x=labels, y=values, marker_color=colors, text=[f"{v:,.1f}" for v in values], textposition="outside")
    )
    return _apply(figure, "Mức đóng góp của từng yếu tố vào nhu cầu (đơn vị)", height=360, show_legend=False)


def risk_figure(plan: list[dict], limit: int = 12) -> go.Figure:
    figure = go.Figure()
    items = [item for item in plan if item.get("stockout_risk", 0) > 0][:limit]
    if items:
        frame = pd.DataFrame(items)
        labels = [
            f"{row.product_name} · {row.region_name}" if row.region_name else str(row.product_name)
            for row in frame.itertuples()
        ]
        figure.add_trace(
            go.Bar(
                x=frame["stockout_risk"],
                y=labels,
                orientation="h",
                marker_color=["#C0392B" if value >= 70 else "#C99A16" for value in frame["stockout_risk"]],
                text=[f"{value:.0f}%" for value in frame["stockout_risk"]],
                textposition="outside",
            )
        )
        figure.update_yaxes(autorange="reversed")
    return _apply(figure, "Điểm rủi ro mất hàng theo sản phẩm / khu vực", height=420, show_legend=False)
