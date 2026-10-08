"""AI giải thích kết quả dự báo và gợi ý hành động."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, helpers, nav, styles
from components.api_client import ApiError

st.set_page_config(page_title="AI Insights · Dự báo nhu cầu", page_icon="🤖", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

styles.page_header(
    "AI giải thích kế hoạch",
    "AI tóm tắt lý do nhu cầu tăng/giảm và gợi ý hành động — chỉ dựa trên số liệu và kết quả dự báo đã tính.",
)

try:
    llm_status = api_client.get("/api/ai/status")
    runs = helpers.load_runs(limit=40, only_completed=True)
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

if llm_status.get("enabled"):
    st.success(
        f"LLM đang bật: **{llm_status.get('provider')}**. "
        "Mọi con số AI đưa ra đều được hậu kiểm lại với số liệu gốc."
    )
else:
    st.info(
        "Chưa cấu hình API key LLM, hệ thống đang dùng **bộ giải thích rule-based** dựa trên chính số liệu dự báo. "
        "Đặt `LLM_PROVIDER=openai` (hoặc `anthropic`) và API key trong `.env` để bật LLM thật."
    )

if not runs:
    st.info("Chưa có lần dự báo nào hoàn thành.")
    nav.page_link("pages/3_Forecast.py", label="Mở trang Dự báo", icon="🔮")
    st.stop()

columns = st.columns([2, 1])
with columns[0]:
    run_id = st.selectbox(
        "Lần dự báo",
        options=[run["id"] for run in runs],
        format_func=lambda value: helpers.run_label(next(run for run in runs if run["id"] == value)),
    )
with columns[1]:
    st.write("")
    force_refresh = st.checkbox("Tạo lại (bỏ qua cache)", value=False)

question = st.text_input(
    "Câu hỏi cụ thể (tùy chọn)",
    placeholder="Ví dụ: Vì sao nhu cầu tháng tới tăng mạnh? Nên làm gì với tồn kho hiện tại?",
)

if st.button("Sinh giải thích", type="primary"):
    try:
        with st.spinner("Đang phân tích số liệu dự báo..."):
            explanation = api_client.post(
                "/api/ai/explain",
                json={"run_id": run_id, "question": question or None, "force_refresh": force_refresh},
            )
        st.session_state["explanation"] = explanation
    except ApiError as exc:
        auth.handle_api_error(exc)

explanation = st.session_state.get("explanation")
if not explanation:
    st.info("Bấm **Sinh giải thích** để tạo phân tích cho lần dự báo đã chọn.")
    st.stop()

if explanation.get("run_id") != run_id:
    st.warning("Phần giải thích bên dưới thuộc một lần dự báo khác. Hãy bấm **Sinh giải thích** lại.")

badges = [
    (explanation.get("provider", "fallback"), "info"),
    (f"Độ tin cậy: {explanation.get('confidence')}", "ok" if explanation.get("confidence") == "high" else "warn"),
]
if explanation.get("cached"):
    badges.append(("Lấy từ cache", "info"))
st.markdown(
    " ".join(f'<span class="pill pill-{kind}">{text}</span>' for text, kind in badges),
    unsafe_allow_html=True,
)
st.write("")

styles.ai_block("Tóm tắt", explanation.get("summary", ""))

columns = st.columns(2)
with columns[0]:
    st.markdown("#### Lý do nhu cầu thay đổi")
    for reason in explanation.get("reasons", []):
        arrow = {"up": "▲", "down": "▼", "flat": "■"}.get(reason.get("direction"), "■")
        color = {"up": "#C0392B", "down": "#2E9E5B", "flat": "#6B7488"}.get(reason.get("direction"), "#6B7488")
        with st.container(border=True):
            st.markdown(
                f"**{reason.get('factor')}** "
                f"<span style='color:{color}'>{arrow} {reason.get('magnitude_pct', 0):.1f}%</span>",
                unsafe_allow_html=True,
            )
            st.caption(reason.get("evidence", ""))

with columns[1]:
    st.markdown("#### Hành động đề xuất")
    for action in explanation.get("recommended_actions", []):
        priority = action.get("priority", "medium")
        kind = {"high": "bad", "medium": "warn", "low": "info"}.get(priority, "info")
        with st.container(border=True):
            st.markdown(f"**{action.get('action')}**")
            st.markdown(f'<span class="pill pill-{kind}">Ưu tiên: {priority}</span>', unsafe_allow_html=True)
            if action.get("owner"):
                st.caption(f"Bộ phận phụ trách: {action['owner']}")
            if action.get("rationale"):
                st.caption(action["rationale"])

if explanation.get("warnings"):
    st.warning("Cảnh báo hậu kiểm số liệu:\n\n" + "\n".join(f"- {item}" for item in explanation["warnings"]))

with st.expander("Số liệu AI được phép sử dụng (grounded numbers)"):
    st.json(explanation.get("grounded_numbers", {}))

with st.expander("Toàn bộ ngữ cảnh số liệu gửi cho AI"):
    try:
        context = api_client.get(f"/api/ai/context/{run_id}")
        st.json(context)
    except ApiError as exc:
        auth.handle_api_error(exc)
