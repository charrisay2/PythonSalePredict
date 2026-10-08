"""Quản lý người dùng (chỉ dành cho quản trị viên)."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, styles
from components.api_client import ApiError

st.set_page_config(page_title="Quản lý người dùng · Dự báo nhu cầu", page_icon="👥", layout="wide")
styles.inject_css()
user = auth.require_login("admin")
auth.render_sidebar()

styles.page_header(
    "Quản lý người dùng",
    "Tạo tài khoản, phân quyền theo vai trò và khóa / mở tài khoản.",
    [("Chỉ quản trị viên", "warn")],
)

ROLE_OPTIONS = ["viewer", "analyst", "admin"]

try:
    users = api_client.get("/api/users")
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

styles.kpi_row(
    [
        {"label": "Tổng người dùng", "value": len(users), "unit": ""},
        {"label": "Quản trị viên", "value": len([u for u in users if u["role"] == "admin"]), "unit": ""},
        {"label": "Chuyên viên phân tích", "value": len([u for u in users if u["role"] == "analyst"]), "unit": ""},
        {"label": "Đang bị khóa", "value": len([u for u in users if not u["is_active"]]), "unit": ""},
    ]
)

tabs = st.tabs(["Danh sách", "Tạo người dùng", "Đặt lại mật khẩu"])

with tabs[0]:
    st.dataframe(
        [
            {
                "ID": item["id"],
                "Email": item["email"],
                "Họ tên": item["full_name"],
                "Vai trò": auth.role_label(item["role"]),
                "Hoạt động": "Có" if item["is_active"] else "Không",
                "Đăng nhập gần nhất": (item.get("last_login_at") or "")[:19].replace("T", " ") or "-",
            }
            for item in users
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.markdown("##### Cập nhật vai trò / trạng thái")
    target = st.selectbox(
        "Người dùng",
        options=[item["id"] for item in users],
        format_func=lambda value: next(
            (f"#{item['id']} · {item['email']}" for item in users if item["id"] == value), str(value)
        ),
        key="update_user_select",
    )
    current = next(item for item in users if item["id"] == target)

    columns = st.columns(3)
    new_role = columns[0].selectbox(
        "Vai trò", options=ROLE_OPTIONS, index=ROLE_OPTIONS.index(current["role"]),
        format_func=auth.role_label, key="update_role"
    )
    new_active = columns[1].checkbox("Đang hoạt động", value=current["is_active"], key="update_active")
    columns[2].write("")
    if columns[2].button("Lưu thay đổi", use_container_width=True):
        try:
            api_client.patch(f"/api/users/{target}", json={"role": new_role, "is_active": new_active})
            st.success("Đã cập nhật người dùng.")
            st.rerun()
        except ApiError as exc:
            auth.handle_api_error(exc)

with tabs[1]:
    st.markdown("##### Tạo tài khoản mới")
    with st.form("create_user_form"):
        columns = st.columns(2)
        email = columns[0].text_input("Email")
        full_name = columns[1].text_input("Họ tên")
        columns2 = st.columns(2)
        password = columns2[0].text_input("Mật khẩu (tối thiểu 8 ký tự)", type="password")
        role = columns2[1].selectbox("Vai trò", options=ROLE_OPTIONS, index=1, format_func=auth.role_label)
        submitted = st.form_submit_button("Tạo người dùng", use_container_width=True, type="primary")

    if submitted:
        if not email or not password:
            st.error("Cần nhập email và mật khẩu.")
        elif len(password) < 8:
            st.error("Mật khẩu phải có ít nhất 8 ký tự.")
        else:
            try:
                created = api_client.post(
                    "/api/users",
                    json={
                        "email": email.strip(),
                        "password": password,
                        "full_name": full_name,
                        "role": role,
                    },
                )
                st.success(f"Đã tạo tài khoản {created['email']} với vai trò {auth.role_label(created['role'])}.")
                st.rerun()
            except ApiError as exc:
                auth.handle_api_error(exc)

with tabs[2]:
    st.markdown("##### Đặt lại mật khẩu")
    st.caption("Quản trị viên có thể đặt lại mật khẩu cho người dùng mà không cần mật khẩu cũ.")
    with st.form("reset_password_form"):
        reset_target = st.selectbox(
            "Người dùng",
            options=[item["id"] for item in users],
            format_func=lambda value: next(
                (f"#{item['id']} · {item['email']}" for item in users if item["id"] == value), str(value)
            ),
        )
        new_password = st.text_input("Mật khẩu mới", type="password")
        ok = st.form_submit_button("Đặt lại mật khẩu", use_container_width=True)
    if ok:
        if len(new_password) < 8:
            st.error("Mật khẩu phải có ít nhất 8 ký tự.")
        else:
            try:
                api_client.post(
                    f"/api/users/{reset_target}/reset-password", params={"new_password": new_password}
                )
                st.success("Đã đặt lại mật khẩu.")
            except ApiError as exc:
                auth.handle_api_error(exc)

st.divider()
st.markdown("##### Đổi mật khẩu của chính bạn")
with st.form("change_own_password"):
    columns = st.columns(2)
    current_password = columns[0].text_input("Mật khẩu hiện tại", type="password")
    own_new_password = columns[1].text_input("Mật khẩu mới", type="password")
    ok = st.form_submit_button("Đổi mật khẩu", use_container_width=True)
if ok:
    try:
        api_client.post(
            "/api/auth/change-password",
            json={"current_password": current_password, "new_password": own_new_password},
        )
        st.success("Đã đổi mật khẩu.")
    except ApiError as exc:
        auth.handle_api_error(exc)
