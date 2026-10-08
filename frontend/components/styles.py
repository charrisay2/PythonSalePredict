"""Giao diện: CSS tùy chỉnh và các thành phần hiển thị dùng chung."""

from __future__ import annotations

import streamlit as st

CUSTOM_CSS = """
<style>
    .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }
    h1, h2, h3 { letter-spacing: -0.01em; }
    div[data-testid="stMetric"] {
        background: #F7F8FC;
        border: 1px solid #E3E7F2;
        border-radius: 12px;
        padding: 14px 16px;
    }
    div[data-testid="stMetricLabel"] p { font-size: 0.82rem; color: #5A6478; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; }
    .app-hero {
        background: linear-gradient(100deg, #EEF0FE 0%, #F7F8FC 60%);
        border: 1px solid #E3E7F2;
        border-radius: 16px;
        padding: 22px 26px;
        margin-bottom: 18px;
    }
    .app-hero h1 { margin: 0 0 6px 0; font-size: 1.6rem; }
    .app-hero p { margin: 0; color: #4C5566; font-size: 0.95rem; }
    .pill {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 500; margin-right: 6px;
    }
    .pill-ok { background: #E4F6EC; color: #14603C; }
    .pill-warn { background: #FDF1DC; color: #8A5A0B; }
    .pill-bad { background: #FBE7E7; color: #8F2222; }
    .pill-info { background: #E8EDFB; color: #2A3E86; }
    .ai-block {
        background: #F7F8FC; border-left: 4px solid #4F46E5;
        border-radius: 10px; padding: 14px 18px; margin-bottom: 12px;
    }
    .ai-block h4 { margin: 0 0 6px 0; font-size: 0.95rem; }
    .ai-block p { margin: 0; font-size: 0.92rem; color: #333B4D; }
    .small-muted { color: #6B7488; font-size: 0.85rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", pills: list[tuple[str, str]] | None = None) -> None:
    """Tiêu đề trang với pill trạng thái. pills = [(nhãn, loại)] với loại: ok|warn|bad|info."""
    pill_html = ""
    for label, kind in pills or []:
        pill_html += f'<span class="pill pill-{kind}">{label}</span>'
    st.markdown(
        f"""
        <div class="app-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
            <div style="margin-top:10px">{pill_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, description: str = "") -> None:
    st.markdown(f"#### {title}")
    if description:
        st.caption(description)


def kpi_row(items: list[dict]) -> None:
    """Hiển thị hàng thẻ KPI. Mỗi item: {label, value, unit, hint}."""
    if not items:
        return
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        value = item.get("value", 0)
        unit = item.get("unit", "")
        if isinstance(value, (int, float)):
            if unit in ("VND",):
                display = f"{value:,.0f} {unit}"
            elif unit == "%":
                display = f"{value:,.1f}%"
            else:
                display = f"{value:,.2f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"
                display = f"{display} {unit}".strip()
        else:
            display = f"{value} {unit}".strip()
        with column:
            st.metric(label=item.get("label", ""), value=display, help=item.get("hint") or None)


def risk_pill(risk: float) -> str:
    if risk >= 70:
        return '<span class="pill pill-bad">Rủi ro cao</span>'
    if risk >= 40:
        return '<span class="pill pill-warn">Cần theo dõi</span>'
    return '<span class="pill pill-ok">An toàn</span>'


def ai_block(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ai-block"><h4>{title}</h4><p>{body}</p></div>',
        unsafe_allow_html=True,
    )


def format_number(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"
