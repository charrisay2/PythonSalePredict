"""So sánh nhiều mô hình dự báo theo sai số backtest."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, charts, helpers, styles
from components.api_client import ApiError

st.set_page_config(page_title="So sánh mô hình · Dự báo nhu cầu", page_icon="⚖️", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

can_run = user.get("role") in ("admin", "analyst")

styles.page_header(
    "So sánh mô hình dự báo",
    "Backtest rolling-origin tất cả mô hình được chọn và xếp hạng theo MAPE, sMAPE, RMSE, MAE, Bias.",
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

available = [item for item in models if item.get("available")]

with st.expander("Cấu hình so sánh", expanded=True):
    with st.form("compare_form"):
        selected_models = st.multiselect(
            "Mô hình cần so sánh",
            options=[item["name"] for item in available],
            default=[item["name"] for item in available],
            format_func=lambda value: next((item["label"] for item in available if item["name"] == value), value),
        )
        columns = st.columns(3)
        horizon = columns[0].slider("Tầm dự báo (ngày)", min_value=7, max_value=90, value=30)
        folds = columns[1].number_input("Số fold backtest", min_value=1, max_value=8, value=3)
        test_size = columns[2].number_input("Số ngày mỗi fold", min_value=7, max_value=90, value=28)
        scope = helpers.scope_selector(catalog, key_prefix="compare_scope")
        submitted = st.form_submit_button(
            "Chạy so sánh", disabled=not can_run, use_container_width=True, type="primary"
        )

if submitted:
    if not selected_models:
        st.error("Hãy chọn ít nhất một mô hình.")
    else:
        try:
            with st.spinner("Đang backtest các mô hình, quá trình này có thể mất vài phút..."):
                payload = {
                    "models": selected_models,
                    "horizon": int(horizon),
                    "backtest_folds": int(folds),
                    "test_size": int(test_size),
                    "granularity": "total",
                    **scope,
                }
                response = api_client.post("/api/forecast/compare", json=payload)
            st.session_state["compare_result"] = response
            st.success("Đã hoàn tất so sánh mô hình.")
        except ApiError as exc:
            auth.handle_api_error(exc)

response = st.session_state.get("compare_result")
if not response:
    st.info("Chạy so sánh để xem bảng xếp hạng. Kết quả của lần chạy gần nhất sẽ được giữ lại.")
    st.stop()

run = response["run"]
leaderboard = response.get("leaderboard", [])
usable = [item for item in leaderboard if not item.get("skipped")]

if run.get("metrics"):
    metrics = run["metrics"]
    styles.kpi_row(
        [
            {"label": "Mô hình tốt nhất", "value": metrics.get("best_model_label", run["model_name"]), "unit": ""},
            {"label": "MAPE tốt nhất", "value": metrics.get("mape"), "unit": "%"},
            {"label": "RMSE tốt nhất", "value": metrics.get("rmse"), "unit": ""},
            {"label": "Độ chính xác ước tính", "value": metrics.get("accuracy"), "unit": "%"},
        ]
    )

if usable:
    st.plotly_chart(charts.leaderboard_figure(leaderboard), use_container_width=True)

st.markdown("#### Bảng xếp hạng chi tiết")
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
            "Độ phủ khoảng tin cậy (%)": item.get("coverage"),
            "Tốt nhất": "✔" if item.get("is_best") else "",
            "Ghi chú": item.get("note") or "",
        }
        for item in leaderboard
    ],
    use_container_width=True,
    hide_index=True,
)

with st.expander("Chi tiết từng fold backtest"):
    for item in usable:
        folds = item.get("folds") or []
        if not folds:
            continue
        st.markdown(f"**{item.get('label')}**")
        st.dataframe(folds, use_container_width=True, hide_index=True)

if run.get("drivers"):
    with st.expander("Yếu tố tác động nhu cầu (trên chuỗi tổng hợp)"):
        st.plotly_chart(charts.drivers_figure(run["drivers"]), use_container_width=True)
