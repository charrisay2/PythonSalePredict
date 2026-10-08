"""Scenario planning: mô phỏng kịch bản what-if."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, charts, helpers, nav, styles
from components.api_client import ApiError

st.set_page_config(page_title="Scenario planning · Dự báo nhu cầu", page_icon="🧪", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

can_run = user.get("role") in ("admin", "analyst")

styles.page_header(
    "Scenario planning",
    "Mô phỏng thay đổi khuyến mãi, giá bán, nhu cầu và thời gian chờ để so sánh với kịch bản cơ sở.",
)

try:
    runs = helpers.load_runs(limit=40, only_completed=True)
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

if not runs:
    st.info("Chưa có lần dự báo nào hoàn thành. Hãy chạy dự báo trước.")
    nav.page_link("pages/3_Forecast.py", label="Mở trang Dự báo", icon="🔮")
    st.stop()

with st.expander("Tạo kịch bản mới", expanded=True):
    base_run_id = st.selectbox(
        "Lần dự báo cơ sở",
        options=[run["id"] for run in runs],
        format_func=lambda value: helpers.run_label(next(run for run in runs if run["id"] == value)),
    )

    with st.form("scenario_form"):
        name = st.text_input("Tên kịch bản", value="Tăng khuyến mãi 20%")
        columns = st.columns(3)
        promo_uplift = columns[0].slider("Thay đổi uplift khuyến mãi (%)", min_value=-50, max_value=150, value=20, step=5)
        price_change = columns[1].slider("Thay đổi giá bán (%)", min_value=-50, max_value=50, value=0, step=5)
        demand_shift = columns[2].slider("Dịch chuyển nhu cầu (%)", min_value=-50, max_value=50, value=0, step=5)

        columns2 = st.columns(3)
        lead_time = columns2[0].number_input("Thời gian chờ mới (ngày)", min_value=0, max_value=180, value=10)
        safety_stock = columns2[1].slider("Thay đổi tồn kho an toàn (%)", min_value=-50, max_value=200, value=20, step=10)
        columns2[2].caption(
            "Độ co giãn giá được áp dụng: -1.1 (giá tăng 1% làm nhu cầu giảm khoảng 1.1%)."
        )

        submitted = st.form_submit_button(
            "Tạo kịch bản", disabled=not can_run, use_container_width=True, type="primary"
        )

    if submitted:
        try:
            payload = {
                "base_run_id": base_run_id,
                "name": name,
                "assumptions": {
                    "promo_uplift_pct": float(promo_uplift),
                    "price_change_pct": float(price_change),
                    "demand_shift_pct": float(demand_shift),
                    "lead_time_days": int(lead_time),
                    "safety_stock_pct": float(safety_stock),
                },
            }
            scenario = api_client.post("/api/scenario", json=payload)
            st.session_state["scenario_id"] = scenario["id"]
            st.success(f"Đã tạo kịch bản #{scenario['id']}.")
            st.rerun()
        except ApiError as exc:
            auth.handle_api_error(exc)

st.divider()

try:
    scenarios = api_client.get("/api/scenario", params={"limit": 30})
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

if not scenarios:
    st.info("Chưa có kịch bản nào.")
    st.stop()

default_index = 0
if st.session_state.get("scenario_id"):
    for index, item in enumerate(scenarios):
        if item["id"] == st.session_state["scenario_id"]:
            default_index = index
            break

scenario_id = st.selectbox(
    "Chọn kịch bản",
    options=[item["id"] for item in scenarios],
    index=default_index,
    format_func=lambda value: f"#{value} · {next(item['name'] for item in scenarios if item['id'] == value)}",
)

try:
    scenario = api_client.get(f"/api/scenario/{scenario_id}")
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

summary = scenario.get("summary") or {}
assumptions = scenario.get("assumptions") or {}

styles.kpi_row(
    [
        {"label": "Nhu cầu cơ sở", "value": summary.get("baseline_total_units"), "unit": "đơn vị"},
        {"label": "Nhu cầu kịch bản", "value": summary.get("scenario_total_units"), "unit": "đơn vị"},
        {"label": "Chênh lệch", "value": summary.get("delta_units"), "unit": "đơn vị"},
        {"label": "Chênh lệch (%)", "value": summary.get("delta_pct"), "unit": "%"},
        {"label": "Ngày cao điểm", "value": summary.get("peak_date") or "-", "unit": ""},
        {"label": "Hàng rủi ro cao", "value": summary.get("high_risk_items", 0), "unit": "mức"},
    ]
)

st.caption(
    f"Giả định: khuyến mãi {assumptions.get('promo_uplift_pct')}% · giá {assumptions.get('price_change_pct')}% · "
    f"nhu cầu {assumptions.get('demand_shift_pct')}% · thời gian chờ {assumptions.get('lead_time_days')} ngày · "
    f"tồn kho an toàn {assumptions.get('safety_stock_pct')}% · hệ số nhu cầu áp dụng {summary.get('demand_factor')}"
)

st.plotly_chart(
    charts.scenario_figure(scenario.get("points", []), scenario.get("name", "Kịch bản")),
    use_container_width=True,
)

st.markdown("#### Kế hoạch tồn kho theo kịch bản")
plan = scenario.get("inventory_plan", [])
if plan:
    st.dataframe(
        [
            {
                "Sản phẩm": item.get("product_name"),
                "Khu vực": item.get("region_name"),
                "Nhu cầu dự báo": item.get("forecast_units"),
                "Nhu cầu/ngày": item.get("daily_demand"),
                "Thời gian chờ": item.get("lead_time_days"),
                "Tồn kho": item.get("on_hand_qty"),
                "Tồn kho an toàn": item.get("safety_stock"),
                "Điểm đặt hàng lại": item.get("reorder_point"),
                "Nên đặt thêm": item.get("suggested_order_qty"),
                "Rủi ro mất hàng (%)": item.get("stockout_risk"),
                "Khuyến nghị": item.get("recommendation"),
            }
            for item in plan[:40]
        ],
        use_container_width=True,
        hide_index=True,
        height=420,
    )
else:
    st.info("Không có dữ liệu kế hoạch tồn kho cho kịch bản này.")

if st.button("Xóa kịch bản này", disabled=not can_run):
    try:
        api_client.delete(f"/api/scenario/{scenario_id}")
        st.session_state.pop("scenario_id", None)
        st.success("Đã xóa kịch bản.")
        st.rerun()
    except ApiError as exc:
        auth.handle_api_error(exc)
