"""Liên kết điều hướng an toàn.

`st.page_link` chỉ hoạt động khi trang đích đã được đăng ký trong entrypoint.
Khi render một trang riêng lẻ (ví dụ trong kiểm thử headless), hàm này tự động
suy giảm thành nhãn văn bản thay vì ném lỗi.
"""

from __future__ import annotations

import streamlit as st


def page_link(path: str, label: str, icon: str | None = None) -> None:
    try:
        st.page_link(path, label=label, icon=icon)
    except Exception:  # noqa: BLE001 - StreamlitPageNotFoundError và các lỗi tương tự
        prefix = f"{icon} " if icon else ""
        st.markdown(f"{prefix}{label}")
