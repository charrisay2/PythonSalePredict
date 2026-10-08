"""Cảnh báo rủi ro mất hàng và tồn kho cao."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, charts, helpers, styles
from components.api_client import ApiError

st.set_page_config(page_title="Cảnh báo · Dự báo nhu cầu", page_icon="🚨", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

can_write = user.get("role") in ("admin", "analyst")

styles.page_header(
    "Cảnh báo rủi ro tồn kho",
    "Danh sách sản phẩm / khu vực có rủi ro mất hàng hoặc tồn kho cao hơn nhu cầu dự báo.",
)

try:
    runs = helpers.load_runs(limit=40, only_completed=True)
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

if not runs:
    st.info("Chưa có lần dự báo nào hoàn thành. Hãy chạy dự báo trước.")
    st.stop()

columns = st.columns([2, 1, 1])
with columns[0]:
    run_id = st.selectbox(
        "Lần dự báo",
        options=[run["id"] for run in runs],
        format_func=lambda value: helpers.run_label(next(run for run in runs if run["id"] == value)),
    )
with columns[1]:
    status_filter = st.selectbox("Trạng thái", options=["all", "open", "ack"], format_func=lambda v: {"all": "Tất cả", "open": "Chưa xử lý", "ack": "Đã xử lý"}[v])
with columns[2]:
    st.write("")
    if st.button("Tính lại cảnh báo", disabled=not can_write, use_container_width=True):
        try:
            with st.spinner("Đang tính lại cảnh báo..."):
                api_client.post("/api/alerts/recompute", params={"run_id": run_id})
            st.success("Đã tính lại cảnh báo.")
            st.rerun()
        except ApiError as exc:
            auth.handle_api_error(exc)

params = {"run_id": run_id}
if status_filter != "all":
    params["status"] = status_filter

try:
    alerts = api_client.get("/api/alerts", params=params)
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

stockouts = [item for item in alerts if item["alert_type"] == "stockout"]
overstocks = [item for item in alerts if item["alert_type"] == "overstock"]

styles.kpi_row(
    [
        {"label": "Tổng cảnh báo", "value": len(alerts), "unit": ""},
        {"label": "Rủi ro mất hàng", "value": len(stockouts), "unit": ""},
        {"label": "Tồn kho cao", "value": len(overstocks), "unit": ""},
        {
            "label": "Điểm rủi ro cao nhất",
            "value": max([item["risk_score"] for item in alerts], default=0.0),
            "unit": "%",
        },
    ]
)

if not alerts:
    st.success("Không có cảnh báo nào trong bộ lọc hiện tại.")
    st.stop()

if stockouts:
    st.plotly_chart(
        charts.risk_figure(
            [
                {
                    "product_name": item.get("product_name") or "Tất cả",
                    "region_name": item.get("region_name"),
                    "stockout_risk": item["risk_score"],
                }
                for item in stockouts
            ]
        ),
        use_container_width=True,
    )

st.markdown("#### Danh sách cảnh báo")
for alert in alerts:
    label = "Mất hàng" if alert["alert_type"] == "stockout" else "Tồn kho cao"
    kind = "bad" if alert["risk_score"] >= 70 else ("warn" if alert["risk_score"] >= 40 else "info")
    with st.container(border=True):
        top = st.columns([3, 1, 1, 1])
        top[0].markdown(
            f"**{label}** · {alert.get('product_name') or 'Tất cả sản phẩm'}"
            f" · {alert.get('region_name') or 'Tất cả khu vực'}"
        )
        top[1].markdown(styles.risk_pill(alert["risk_score"]), unsafe_allow_html=True)
        top[2].metric("Điểm rủi ro", f"{alert['risk_score']:.1f}%")
        top[3].metric("Mức độ", alert["severity"])
        st.caption(alert["message"])
        if alert["status"] == "open" and can_write:
            if st.button("Đánh dấu đã xử lý", key=f"ack_{alert['id']}"):
                try:
                    api_client.patch(f"/api/alerts/{alert['id']}/ack")
                    st.rerun()
                except ApiError as exc:
                    auth.handle_api_error(exc)
        elif alert["status"] == "ack":
            st.caption("Đã xử lý")
