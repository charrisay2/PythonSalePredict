"""Dashboard tổng quan."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, charts, helpers, nav, styles
from components.api_client import ApiError

st.set_page_config(page_title="Dashboard · Dự báo nhu cầu", page_icon="📊", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

styles.page_header(
    "Dashboard tổng quan",
    "Bức tranh nhu cầu bán hàng, chất lượng dự báo và các rủi ro tồn kho đang mở.",
)

try:
    summary = api_client.get("/api/dashboard/summary")
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

if summary.get("date_start"):
    st.caption(
        f"Dữ liệu từ **{summary['date_start']}** đến **{summary['date_end']}** · "
        f"{summary.get('active_products', 0)} sản phẩm đang hoạt động"
    )

styles.kpi_row(summary.get("kpis", []))

left, right = st.columns([1.6, 1])
with left:
    st.plotly_chart(charts.monthly_series_figure(summary.get("monthly_series", [])), use_container_width=True)
with right:
    st.plotly_chart(charts.top_products_figure(summary.get("top_products", [])), use_container_width=True)

st.divider()
st.markdown("#### Các lần dự báo gần đây")
recent = summary.get("recent_runs", [])
if not recent:
    st.info("Chưa có lần dự báo nào. Hãy vào trang **Dự báo** để chạy mô hình đầu tiên.")
else:
    st.dataframe(
        [
            {
                "ID": run["id"],
                "Tên": run["name"],
                "Trạng thái": run["status"],
                "Mô hình": run["model_name"],
                "Độ chi tiết": run["granularity"],
                "Tầm dự báo": run["horizon"],
                "MAPE (%)": run.get("mape"),
                "Tạo lúc": (run.get("created_at") or "")[:19].replace("T", " "),
            }
            for run in recent
        ],
        use_container_width=True,
        hide_index=True,
    )

if summary.get("open_alerts"):
    st.warning(f"Đang có **{summary['open_alerts']}** cảnh báo chưa xử lý. Xem chi tiết ở trang **Cảnh báo**.")
    nav.page_link("pages/6_Alerts.py", label="Mở trang Cảnh báo", icon="🚨")

if user.get("role") in ("admin", "analyst"):
    st.divider()
    st.markdown("#### Thao tác nhanh")
    columns = st.columns(3)
    with columns[0]:
        nav.page_link("pages/3_Forecast.py", label="Chạy dự báo mới", icon="🔮")
    with columns[1]:
        nav.page_link("pages/4_Model_Compare.py", label="So sánh mô hình", icon="⚖️")
    with columns[2]:
        nav.page_link("pages/7_AI_Insights.py", label="Xem AI giải thích", icon="🤖")
