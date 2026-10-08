"""Huấn luyện mô hình và xem kết quả dự báo."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, charts, helpers, nav, styles
from components.api_client import ApiError

st.set_page_config(page_title="Dự báo · Dự báo nhu cầu", page_icon="🔮", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

can_run = user.get("role") in ("admin", "analyst")

styles.page_header(
    "Dự báo nhu cầu",
    "Huấn luyện nhiều mô hình, chọn mô hình tốt nhất theo backtest và xem kết quả dự báo.",
)

try:
    stats = api_client.get("/api/data/stats")
    catalog = helpers.load_catalog()
    models = helpers.load_models()
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

if not helpers.require_data_available(stats):
    st.stop()

available_models = [item for item in models if item.get("available")]
unavailable_models = [item for item in models if not item.get("available")]

with st.expander("Cấu hình lần dự báo", expanded=True):
    with st.form("forecast_form"):
        columns = st.columns(3)
        name = columns[0].text_input("Tên lần dự báo", value="Dự báo nhu cầu")
        horizon = columns[1].slider("Tầm dự báo (ngày)", min_value=7, max_value=180, value=30, step=1)
        granularity = columns[2].selectbox(
            "Độ chi tiết",
            options=["total", "product", "region", "channel", "product_region"],
            format_func=lambda value: {
                "total": "Tổng hợp toàn bộ",
                "product": "Theo sản phẩm",
                "region": "Theo khu vực",
                "channel": "Theo kênh bán",
                "product_region": "Theo sản phẩm × khu vực",
            }[value],
        )

        selected_models = st.multiselect(
            "Mô hình huấn luyện",
            options=[item["name"] for item in available_models],
            default=[item["name"] for item in available_models if item["name"] in ("seasonal_naive", "prophet", "gradient_boosting")],
            format_func=lambda value: next((item["label"] for item in available_models if item["name"] == value), value),
            help="Hệ thống backtest tất cả mô hình được chọn và lấy mô hình có sai số MAPE thấp nhất.",
        )

        scope = helpers.scope_selector(catalog, key_prefix="forecast_scope")

        columns2 = st.columns(2)
        folds = columns2[0].number_input("Số fold backtest", min_value=1, max_value=8, value=3)
        test_size = columns2[1].number_input("Số ngày mỗi fold", min_value=7, max_value=120, value=28)

        submitted = st.form_submit_button(
            "Chạy dự báo", disabled=not can_run, use_container_width=True, type="primary"
        )

    if unavailable_models:
        st.caption(
            "Mô hình không khả dụng: "
            + "; ".join(f"{item['label']} ({item['reason']})" for item in unavailable_models)
        )

if submitted:
    if not selected_models:
        st.error("Hãy chọn ít nhất một mô hình.")
    else:
        try:
            payload = {
                "name": name,
                "models": selected_models,
                "horizon": int(horizon),
                "granularity": granularity,
                "backtest_folds": int(folds),
                "test_size": int(test_size),
                "wait": False,
                **scope,
            }
            run = api_client.post("/api/forecast/train", json=payload)
            final = helpers.poll_run(run["id"])
            if final.get("status") == "failed":
                st.error(f"Dự báo thất bại: {final.get('error_message')}")
            else:
                st.session_state["active_run_id"] = final["id"]
                st.success(
                    f"Hoàn tất! Mô hình tốt nhất: **{final['model_name']}** · "
                    f"MAPE {final['metrics']['mape']}% · Độ chính xác {final['metrics']['accuracy']}%"
                )
                st.rerun()
        except ApiError as exc:
            auth.handle_api_error(exc)

st.divider()

runs = helpers.load_runs(limit=40, only_completed=True)
if not runs:
    st.info("Chưa có lần dự báo nào hoàn thành.")
    st.stop()

default_index = 0
if st.session_state.get("active_run_id"):
    for index, run in enumerate(runs):
        if run["id"] == st.session_state["active_run_id"]:
            default_index = index
            break

selected_run_id = st.selectbox(
    "Chọn lần dự báo để xem",
    options=[run["id"] for run in runs],
    index=default_index,
    format_func=lambda value: helpers.run_label(next(run for run in runs if run["id"] == value)),
)

try:
    result = api_client.get(f"/api/forecast/runs/{selected_run_id}/result", params={"history_days": 120})
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

run = result["run"]
metrics = run.get("metrics") or {}
drivers = run.get("drivers") or {}

styles.kpi_row(
    [
        {"label": "Mô hình tốt nhất", "value": run["model_name"], "unit": "", "hint": "Chọn theo MAPE thấp nhất"},
        {"label": "Tổng nhu cầu dự báo", "value": result["total_forecast_units"], "unit": "đơn vị"},
        {"label": "MAPE", "value": metrics.get("mape"), "unit": "%", "hint": "Sai số phần trăm tuyệt đối trung bình"},
        {"label": "Độ chính xác ước tính", "value": metrics.get("accuracy"), "unit": "%"},
        {"label": "RMSE", "value": metrics.get("rmse"), "unit": ""},
        {"label": "Bias", "value": metrics.get("bias"), "unit": "", "hint": "Dương = dự báo cao hơn thực tế"},
    ]
)

st.plotly_chart(
    charts.forecast_figure(result.get("history", []), result.get("points", [])),
    use_container_width=True,
)

columns = st.columns([1, 1])
with columns[0]:
    st.plotly_chart(charts.drivers_figure(drivers), use_container_width=True)
with columns[1]:
    st.markdown("#### Yếu tố tác động")
    st.markdown(
        f"""
- **Xu hướng gần đây:** {styles.format_number(drivers.get('trend_delta_units'))} đơn vị ({drivers.get('trend_delta_pct')}%)
- **Biến động theo thứ:** {styles.format_number(drivers.get('weekly_amplitude_units'))} đơn vị ({drivers.get('weekly_amplitude_pct')}%)
- **Ngày lễ:** {styles.format_number(drivers.get('holiday_lift_units'))} đơn vị
- **Khuyến mãi:** {styles.format_number(drivers.get('promo_lift_units'))} đơn vị
- **Nền trung bình:** {styles.format_number(drivers.get('baseline_mean'))} đơn vị/ngày
- **Số quan sát:** {drivers.get('n_observations', '-')}
        """
    )

with st.expander("Bảng xếp hạng mô hình của lần dự báo này"):
    leaderboard = run.get("leaderboard") or []
    if leaderboard:
        st.dataframe(
            [
                {
                    "Hạng": item.get("rank"),
                    "Mô hình": item.get("label"),
                    "MAPE (%)": item.get("mape"),
                    "sMAPE (%)": item.get("smape"),
                    "RMSE": item.get("rmse"),
                    "MAE": item.get("mae"),
                    "Bias": item.get("bias"),
                    "Tốt nhất": "✔" if item.get("is_best") else "",
                    "Ghi chú": item.get("note") or "",
                }
                for item in leaderboard
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Không có dữ liệu xếp hạng.")

with st.expander("Chi tiết điểm dự báo"):
    points = result.get("points", [])
    if points:
        st.dataframe(points, use_container_width=True, hide_index=True, height=320)
    else:
        st.info("Không có điểm dự báo.")

columns = st.columns(2)
with columns[0]:
    nav.page_link("pages/7_AI_Insights.py", label="Xem AI giải thích kết quả này", icon="🤖")
with columns[1]:
    nav.page_link("pages/5_Scenario.py", label="Mô phỏng kịch bản what-if", icon="🧪")
