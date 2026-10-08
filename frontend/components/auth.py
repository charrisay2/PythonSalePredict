"""Quản lý phiên đăng nhập và phân quyền trên giao diện."""

from __future__ import annotations

import streamlit as st

from components import api_client, nav
from components.api_client import ApiError

ROLE_LABELS = {
    "admin": "Quản trị viên",
    "analyst": "Chuyên viên phân tích",
    "viewer": "Người xem",
}

ROLE_ORDER = {"viewer": 0, "analyst": 1, "admin": 2}


def login(email: str, password: str) -> dict:
    payload = api_client.post("/api/auth/login", json={"email": email, "password": password})
    st.session_state["token"] = payload["access_token"]
    st.session_state["user"] = payload["user"]
    return payload["user"]


def logout() -> None:
    for key in ("token", "user", "active_run_id", "scenario_id"):
        st.session_state.pop(key, None)


def is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


def current_user() -> dict | None:
    return st.session_state.get("user")


def role_label(role: str | None) -> str:
    return ROLE_LABELS.get(role or "", role or "-")


def has_role(minimum_role: str) -> bool:
    user = current_user()
    if not user:
        return False
    return ROLE_ORDER.get(user.get("role", ""), -1) >= ROLE_ORDER.get(minimum_role, 99)


def require_login(minimum_role: str | None = None) -> dict:
    """Chặn truy cập nếu chưa đăng nhập hoặc không đủ quyền."""
    if not is_logged_in():
        st.warning("Bạn cần đăng nhập để sử dụng chức năng này.")
        st.page_link("app.py", label="Về trang đăng nhập", icon="🔐")
        st.stop()

    user = current_user() or {}
    if minimum_role and not has_role(minimum_role):
        st.error(
            f"Chức năng này cần quyền '{ROLE_LABELS.get(minimum_role, minimum_role)}' trở lên. "
            f"Vai trò hiện tại của bạn: {role_label(user.get('role'))}."
        )
        st.stop()
    return user


def render_sidebar() -> None:
    """Hiển thị thông tin người dùng ở sidebar."""
    user = current_user() or {}
    with st.sidebar:
        st.markdown("### Nền tảng dự báo nhu cầu")
        if user:
            st.markdown(f"**{user.get('full_name') or user.get('email')}**")
            st.caption(f"{user.get('email')} · {role_label(user.get('role'))}")
        st.divider()

        if st.button("Đăng xuất", use_container_width=True):
            logout()
            st.rerun()


def handle_api_error(exc: Exception) -> None:
    if isinstance(exc, ApiError):
        st.error(exc.message)
    else:  # pragma: no cover
        st.error(f"Lỗi không mong đợi: {exc}")
