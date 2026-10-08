"""Xuất báo cáo dự báo (Excel / PDF / CSV)."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, charts, helpers, nav, styles
from components.api_client import ApiError

st.set_page_config(page_title="Báo cáo · Dự báo nhu cầu", page_icon="📄", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

styles.page_header(
    "Báo cáo",
    "Xuất báo cáo dự báo đầy đủ (tổng quan, bảng xếp hạng mô hình, chi tiết, cảnh báo, kế hoạch tồn kho).",
)

try:
    runs = helpers.load_runs(limit=40, only_completed=True)
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

if not runs:
    st.info("Chưa có lần dự báo nào hoàn thành.")
    nav.page_link("pages/3_Forecast.py", label="Mở trang Dự báo", icon="🔮")
    st.stop()

run_id = st.selectbox(
    "Chọn lần dự báo",
    options=[run["id"] for run in runs],
    format_func=lambda value: helpers.run_label(next(run for run in runs if run["id"] == value)),
)

try:
    run = api_client.get(f"/api/forecast/runs/{run_id}")
    result = api_client.get(f"/api/forecast/runs/{run_id}/result", params={"history_days": 90})
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

metrics = run.get("metrics") or {}
drivers = run.get("drivers") or {}

styles.kpi_row(
    [
        {"label": "Mô hình", "value": run["model_name"], "unit": ""},
        {"label": "Tầm dự báo", "value": run["horizon"], "unit": "ngày"},
        {"label": "MAPE", "value": metrics.get("mape"), "unit": "%"},
        {"label": "Độ chính xác", "value": metrics.get("accuracy"), "unit": "%"},
        {"label": "Tổng nhu cầu dự báo", "value": result["total_forecast_units"], "unit": "đơn vị"},
    ]
)

st.markdown("#### Tải báo cáo")
columns = st.columns(3)
formats = [
    ("xlsx", "Excel (.xlsx)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("pdf", "PDF (.pdf)", "application/pdf"),
    ("csv", "CSV (.csv)", "text/csv"),
]
for column, (fmt, label, mime) in zip(columns, formats):
    with column:
        if st.button(f"Chuẩn bị {label}", use_container_width=True):
            try:
                content = api_client.get(
                    f"/api/reports/runs/{run_id}/export", params={"format": fmt}, raw=True
                )
                st.session_state[f"report_{fmt}"] = content
            except ApiError as exc:
                auth.handle_api_error(exc)
        if st.session_state.get(f"report_{fmt}"):
            st.download_button(
                f"Tải {label}",
                data=st.session_state[f"report_{fmt}"],
                file_name=f"bao-cao-du-bao-{run_id}.{fmt}",
                mime=mime,
                use_container_width=True,
            )

st.divider()
st.markdown("#### Xem trước nội dung báo cáo")

st.plotly_chart(
    charts.forecast_figure(result.get("history", []), result.get("points", [])),
    use_container_width=True,
)

left, right = st.columns(2)
with left:
    st.markdown("##### Bảng xếp hạng mô hình")
    leaderboard = run.get("leaderboard") or []
    if leaderboard:
        st.dataframe(
            [
                {
                    "Hạng": item.get("rank"),
                    "Mô hình": item.get("label"),
                    "MAPE (%)": item.get("mape"),
                    "RMSE": item.get("rmse"),
                    "Tốt nhất": "✔" if item.get("is_best") else "",
                }
                for item in leaderboard
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Không có dữ liệu.")

with right:
    st.markdown("##### Yếu tố tác động nhu cầu")
    st.markdown(
        f"""
- Xu hướng: **{styles.format_number(drivers.get('trend_delta_units'))}** đơn vị ({drivers.get('trend_delta_pct')}%)
- Mùa vụ tuần: **{styles.format_number(drivers.get('weekly_amplitude_units'))}** đơn vị ({drivers.get('weekly_amplitude_pct')}%)
- Ngày lễ: **{styles.format_number(drivers.get('holiday_lift_units'))}** đơn vị
- Khuyến mãi: **{styles.format_number(drivers.get('promo_lift_units'))}** đơn vị
- Nền trung bình: **{styles.format_number(drivers.get('baseline_mean'))}** đơn vị/ngày
        """
    )

with st.expander("Chi tiết điểm dự báo"):
    st.dataframe(result.get("points", []), use_container_width=True, hide_index=True, height=320)
