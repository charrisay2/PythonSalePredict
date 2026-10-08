"""Trang chủ: đăng nhập và điều hướng nhanh."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, nav, styles
from components.api_client import ApiError

st.set_page_config(
    page_title="Nền tảng dự báo nhu cầu bán hàng",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject_css()

PAGES = [
    ("pages/1_Dashboard.py", "Dashboard", "Tổng quan KPI, sản lượng, doanh thu và độ chính xác dự báo"),
    ("pages/2_Data.py", "Dữ liệu", "Nạp CSV, sinh dữ liệu mẫu, quản lý danh mục và tồn kho"),
    ("pages/3_Forecast.py", "Dự báo", "Huấn luyện mô hình và xem kết quả dự báo theo phạm vi"),
    ("pages/4_Model_Compare.py", "So sánh mô hình", "Backtest nhiều mô hình và xếp hạng theo sai số"),
    ("pages/5_Scenario.py", "Scenario planning", "Mô phỏng kịch bản khuyến mãi / giá / tồn kho"),
    ("pages/6_Alerts.py", "Cảnh báo", "Rủi ro mất hàng và tồn kho cao"),
    ("pages/7_AI_Insights.py", "AI Insights", "AI giải thích lý do tăng/giảm và gợi ý hành động"),
    ("pages/8_Reports.py", "Báo cáo", "Xuất báo cáo Excel, PDF, CSV"),
    ("pages/9_Admin_Users.py", "Quản lý người dùng", "Tạo tài khoản, phân quyền, khóa/mở tài khoản"),
]


def render_login() -> None:
    left, right = st.columns([1.15, 1])
    with left:
        styles.page_header(
            "Nền tảng dự báo nhu cầu bán hàng",
            "Time series + Machine Learning + AI giải thích kế hoạch cho doanh nghiệp bán lẻ.",
            [("Prophet", "info"), ("scikit-learn", "info"), ("FastAPI", "info"), ("PostgreSQL", "info")],
        )
        st.markdown(
            """
**Nền tảng này giúp bạn:**

- Dự báo nhu cầu theo sản phẩm, khu vực, kênh bán và chương trình khuyến mãi
- So sánh sai số giữa nhiều mô hình (Prophet, Gradient Boosting, Random Forest, SARIMA, baseline)
- AI tóm tắt **lý do nhu cầu tăng/giảm** và gợi ý hành động điều chỉnh tồn kho / khuyến mãi
- Mô phỏng kịch bản (what-if), cảnh báo rủi ro mất hàng, xuất báo cáo Excel / PDF
            """
        )
        st.info(
            "Tài khoản demo: **admin@example.com** / **Admin@12345** "
            "(có thể đổi trong file `.env`)."
        )

    with right:
        st.markdown("### Đăng nhập")
        with st.form("login_form"):
            email = st.text_input("Email", value="admin@example.com")
            password = st.text_input("Mật khẩu", value="Admin@12345", type="password")
            submitted = st.form_submit_button("Đăng nhập", use_container_width=True)

        if submitted:
            try:
                user = auth.login(email.strip(), password)
                st.success(f"Xin chào {user.get('full_name') or user.get('email')}!")
                st.rerun()
            except ApiError as exc:
                auth.handle_api_error(exc)

        status = api_client.health()
        if status:
            st.caption(
                f"API: {api_client.get_base_url()} · CSDL: {status.get('database')} · "
                f"LLM: {'bật' if status.get('llm_enabled') else 'fallback rule-based'}"
            )
        else:
            st.error(
                f"Không kết nối được API tại {api_client.get_base_url()}. "
                "Hãy chạy backend: `uvicorn app.main:app --reload` trong thư mục `backend/`."
            )


def render_home() -> None:
    user = auth.current_user() or {}
    auth.render_sidebar()
    styles.page_header(
        f"Xin chào, {user.get('full_name') or user.get('email')}",
        "Chọn một chức năng để bắt đầu. Bạn có thể bắt đầu từ Dashboard hoặc sinh dữ liệu mẫu.",
        [(auth.role_label(user.get("role")), "info")],
    )

    try:
        summary = api_client.get("/api/dashboard/summary")
    except ApiError as exc:
        auth.handle_api_error(exc)
        return

    styles.kpi_row(summary.get("kpis", [])[:3])

    st.markdown("#### Chức năng")
    columns = st.columns(3)
    for index, (path, title, description) in enumerate(PAGES):
        with columns[index % 3]:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(description)
                nav.page_link(path, label="Mở trang", icon="➡️")


if auth.is_logged_in():
    render_home()
else:
    render_login()
