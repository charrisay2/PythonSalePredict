"""Quản lý dữ liệu: nạp CSV, sinh dữ liệu mẫu, danh mục và tồn kho."""

from __future__ import annotations

import streamlit as st

from components import api_client, auth, helpers, styles
from components.api_client import ApiError

st.set_page_config(page_title="Dữ liệu · Dự báo nhu cầu", page_icon="🗂️", layout="wide")
styles.inject_css()
user = auth.require_login()
auth.render_sidebar()

can_write = user.get("role") in ("admin", "analyst")

styles.page_header(
    "Dữ liệu bán hàng",
    "Nạp dữ liệu lịch sử, sinh dữ liệu mẫu, quản lý danh mục sản phẩm / khu vực / kênh và tồn kho.",
    [("Có quyền ghi" if can_write else "Chỉ xem", "ok" if can_write else "warn")],
)

try:
    stats = api_client.get("/api/data/stats")
except ApiError as exc:
    auth.handle_api_error(exc)
    st.stop()

styles.kpi_row(
    [
        {"label": "Bản ghi bán hàng", "value": stats["total_rows"], "unit": "", "hint": "Số dòng trong bảng sales"},
        {"label": "Tổng sản lượng", "value": stats["total_units"], "unit": "đơn vị"},
        {"label": "Tổng doanh thu", "value": stats["total_revenue"], "unit": "VND"},
        {"label": "Khoảng thời gian", "value": f"{stats['date_start'] or '-'} → {stats['date_end'] or '-'}", "unit": ""},
    ]
)

tabs = st.tabs(["Tổng quan", "Sinh dữ liệu mẫu", "Nạp CSV", "Danh mục", "Ngày lễ & Khuyến mãi", "Tồn kho"])

# ---------------------------------------------------------------------------
with tabs[0]:
    st.markdown("#### Chuỗi sản lượng theo ngày")
    days = st.slider("Số ngày hiển thị", min_value=30, max_value=730, value=180, step=30, key="overview_days")
    try:
        series = api_client.get("/api/data/daily-series", params={"last_n": days})
        items = series.get("items", [])
        if items:
            import plotly.graph_objects as go

            figure = go.Figure()
            figure.add_trace(
                go.Scatter(
                    x=[item["ds"] for item in items],
                    y=[item["y"] for item in items],
                    name="Sản lượng",
                    mode="lines",
                    line=dict(color="#4F46E5", width=2),
                )
            )
            figure.update_layout(
                template="plotly_white",
                height=380,
                margin=dict(l=10, r=10, t=30, b=10),
                title="Sản lượng bán ra theo ngày",
            )
            st.plotly_chart(figure, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu.")
    except ApiError as exc:
        auth.handle_api_error(exc)

# ---------------------------------------------------------------------------
with tabs[1]:
    st.markdown("#### Sinh bộ dữ liệu bán hàng mẫu")
    st.caption(
        "Bộ dữ liệu mô phỏng có mùa vụ theo tuần/năm, ngày lễ, chương trình khuyến mãi, "
        "4 khu vực và 3 kênh bán — dùng để demo toàn bộ hệ thống."
    )
    with st.form("sample_form"):
        columns = st.columns(4)
        days = columns[0].number_input("Số ngày", min_value=120, max_value=1825, value=540, step=30)
        products = columns[1].number_input("Số sản phẩm", min_value=1, max_value=10, value=10)
        regions = columns[2].number_input("Số khu vực", min_value=1, max_value=4, value=4)
        channels = columns[3].number_input("Số kênh bán", min_value=1, max_value=3, value=3)
        reset = st.checkbox("Xóa dữ liệu cũ trước khi sinh (khuyến nghị)", value=True)
        submitted = st.form_submit_button("Sinh dữ liệu mẫu", disabled=not can_write, use_container_width=True)

    if submitted:
        try:
            with st.spinner("Đang sinh dữ liệu, vui lòng đợi..."):
                result = api_client.post(
                    "/api/data/generate-sample",
                    json={
                        "days": int(days),
                        "products": int(products),
                        "regions": int(regions),
                        "channels": int(channels),
                        "reset": bool(reset),
                    },
                )
            st.success(
                f"Đã tạo {result['rows_inserted']:,} dòng "
                f"({result['date_start']} → {result['date_end']})."
            )
            st.rerun()
        except ApiError as exc:
            auth.handle_api_error(exc)

# ---------------------------------------------------------------------------
with tabs[2]:
    st.markdown("#### Nạp dữ liệu bán hàng từ CSV")
    st.caption(
        "Cột bắt buộc: `sale_date` (hoặc `date`/`ngay`) và `quantity` (hoặc `qty`/`so_luong`). "
        "Cột tùy chọn: `sku`, `region`, `channel`, `unit_price`, `discount_pct`, `revenue`, `is_holiday`."
    )
    uploaded = st.file_uploader("Chọn file CSV", type=["csv"], disabled=not can_write)
    if uploaded is not None and st.button("Nạp dữ liệu", disabled=not can_write):
        try:
            with st.spinner("Đang nạp dữ liệu..."):
                result = api_client.upload("/api/data/upload", uploaded.name, uploaded.getvalue())
            st.success(
                f"Đã nạp {result['rows_inserted']:,}/{result['rows_received']:,} dòng "
                f"(bỏ qua {result['rows_skipped']})."
            )
            if result.get("errors"):
                st.warning("\n".join(result["errors"]))
            st.rerun()
        except ApiError as exc:
            auth.handle_api_error(exc)

    st.divider()
    st.markdown("##### Tải file CSV mẫu từ dữ liệu hiện có")
    if st.button("Xuất CSV mẫu (5.000 dòng)"):
        try:
            runs = helpers.load_runs(limit=1, only_completed=True)
            if not runs:
                st.info("Hãy chạy một lần dự báo trước, hoặc dùng tab 'Sinh dữ liệu mẫu'.")
            else:
                run_id = runs[0]["id"]
                content = api_client.get(f"/api/reports/runs/{run_id}/export", params={"format": "csv"}, raw=True)
                st.download_button("Tải xuống", data=content, file_name="du-lieu-mau.csv", mime="text/csv")
        except ApiError as exc:
            auth.handle_api_error(exc)

# ---------------------------------------------------------------------------
with tabs[3]:
    try:
        catalog = helpers.load_catalog()
    except ApiError as exc:
        auth.handle_api_error(exc)
        st.stop()

    columns = st.columns(3)
    with columns[0]:
        st.markdown("##### Sản phẩm")
        st.dataframe(
            [
                {"SKU": item["sku"], "Tên": item["name"], "Nhóm": item["category"], "Giá": item["unit_price"], "Hoạt động": item["is_active"]}
                for item in catalog["products"]
            ],
            use_container_width=True,
            hide_index=True,
            height=280,
        )
    with columns[1]:
        st.markdown("##### Khu vực")
        st.dataframe(
            [{"Mã": item["code"], "Tên": item["name"], "Hệ số nhu cầu": item["demand_factor"]} for item in catalog["regions"]],
            use_container_width=True,
            hide_index=True,
            height=280,
        )
    with columns[2]:
        st.markdown("##### Kênh bán")
        st.dataframe(
            [{"Mã": item["code"], "Tên": item["name"], "Hệ số nhu cầu": item["demand_factor"]} for item in catalog["channels"]],
            use_container_width=True,
            hide_index=True,
            height=280,
        )

    if can_write:
        st.divider()
        st.markdown("##### Thêm sản phẩm mới")
        with st.form("product_form"):
            row = st.columns(4)
            sku = row[0].text_input("SKU")
            name = row[1].text_input("Tên sản phẩm")
            category = row[2].text_input("Nhóm hàng", value="General")
            price = row[3].number_input("Đơn giá", min_value=0.0, value=50000.0, step=1000.0)
            row2 = st.columns(4)
            cost = row2[0].number_input("Giá vốn", min_value=0.0, value=32000.0, step=1000.0)
            lead_time = row2[1].number_input("Thời gian chờ (ngày)", min_value=0, max_value=365, value=7)
            seasonal = row2[2].checkbox("Có tính mùa vụ", value=False)
            submitted = row2[3].form_submit_button("Thêm sản phẩm", use_container_width=True)
        if submitted:
            if not sku or not name:
                st.error("Cần nhập SKU và tên sản phẩm.")
            else:
                try:
                    api_client.post(
                        "/api/data/products",
                        json={
                            "sku": sku.strip(),
                            "name": name.strip(),
                            "category": category,
                            "unit_price": price,
                            "unit_cost": cost,
                            "lead_time_days": int(lead_time),
                            "is_seasonal": bool(seasonal),
                        },
                    )
                    st.success("Đã thêm sản phẩm.")
                    st.rerun()
                except ApiError as exc:
                    auth.handle_api_error(exc)

# ---------------------------------------------------------------------------
with tabs[4]:
    columns = st.columns(2)
    try:
        holidays = api_client.get("/api/data/holidays")
        promos = api_client.get("/api/data/promos")
    except ApiError as exc:
        auth.handle_api_error(exc)
        st.stop()

    with columns[0]:
        st.markdown("##### Ngày lễ / sự kiện")
        st.dataframe(
            [
                {"Tên": item["name"], "Ngày": item["holiday_date"], "Hệ số tác động": item["impact_factor"], "Lặp hằng năm": item["is_recurring_yearly"]}
                for item in holidays
            ],
            use_container_width=True,
            hide_index=True,
            height=320,
        )
    with columns[1]:
        st.markdown("##### Chương trình khuyến mãi")
        st.dataframe(
            [
                {"Tên": item["name"], "Từ": item["start_date"], "Đến": item["end_date"], "Giảm (%)": item["discount_pct"], "Hệ số nhu cầu": item["uplift_factor"]}
                for item in promos
            ],
            use_container_width=True,
            hide_index=True,
            height=320,
        )

    if can_write:
        st.divider()
        left, right = st.columns(2)
        with left:
            st.markdown("##### Thêm ngày lễ")
            with st.form("holiday_form"):
                name = st.text_input("Tên ngày lễ")
                holiday_date = st.date_input("Ngày")
                impact = st.number_input("Hệ số tác động nhu cầu", min_value=0.5, max_value=3.0, value=1.3, step=0.05)
                recurring = st.checkbox("Lặp lại hằng năm", value=True)
                ok = st.form_submit_button("Thêm ngày lễ", use_container_width=True)
            if ok and name:
                try:
                    api_client.post(
                        "/api/data/holidays",
                        json={
                            "name": name,
                            "holiday_date": holiday_date.isoformat(),
                            "impact_factor": impact,
                            "is_recurring_yearly": recurring,
                        },
                    )
                    st.success("Đã thêm ngày lễ.")
                    st.rerun()
                except ApiError as exc:
                    auth.handle_api_error(exc)

        with right:
            st.markdown("##### Thêm khuyến mãi")
            with st.form("promo_form"):
                promo_name = st.text_input("Tên chương trình")
                start = st.date_input("Bắt đầu")
                end = st.date_input("Kết thúc")
                discount = st.number_input("Mức giảm giá (%)", min_value=0.0, max_value=90.0, value=15.0, step=1.0)
                uplift = st.number_input("Hệ số tăng nhu cầu", min_value=1.0, max_value=3.0, value=1.25, step=0.05)
                ok = st.form_submit_button("Thêm khuyến mãi", use_container_width=True)
            if ok and promo_name:
                try:
                    api_client.post(
                        "/api/data/promos",
                        json={
                            "name": promo_name,
                            "start_date": start.isoformat(),
                            "end_date": end.isoformat(),
                            "discount_pct": discount,
                            "uplift_factor": uplift,
                        },
                    )
                    st.success("Đã thêm khuyến mãi.")
                    st.rerun()
                except ApiError as exc:
                    auth.handle_api_error(exc)

# ---------------------------------------------------------------------------
with tabs[5]:
    st.markdown("#### Tồn kho hiện tại")
    try:
        inventory = api_client.get("/api/data/inventory")
        catalog = helpers.load_catalog()
    except ApiError as exc:
        auth.handle_api_error(exc)
        st.stop()

    products = {item["id"]: item["name"] for item in catalog["products"]}
    regions = {item["id"]: item["name"] for item in catalog["regions"]}
    if inventory:
        st.dataframe(
            [
                {
                    "Sản phẩm": products.get(item["product_id"], item["product_id"]),
                    "Khu vực": regions.get(item["region_id"], item["region_id"]),
                    "Tồn kho": item["on_hand_qty"],
                    "Tồn kho an toàn": item["safety_stock"],
                    "Hàng đang về": item["incoming_qty"],
                }
                for item in inventory
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Chưa có dữ liệu tồn kho. Hãy sinh dữ liệu mẫu hoặc thêm bản ghi bên dưới.")

    if can_write:
        st.divider()
        st.markdown("##### Cập nhật tồn kho")
        with st.form("inventory_form"):
            columns = st.columns(4)
            product_id = columns[0].selectbox(
                "Sản phẩm", options=list(products.keys()), format_func=lambda value: products[value]
            )
            region_id = columns[1].selectbox(
                "Khu vực", options=list(regions.keys()), format_func=lambda value: regions[value]
            )
            on_hand = columns[2].number_input("Tồn kho", min_value=0.0, value=100.0, step=10.0)
            safety = columns[3].number_input("Tồn kho an toàn", min_value=0.0, value=30.0, step=5.0)
            incoming = st.number_input("Hàng đang về", min_value=0.0, value=0.0, step=10.0)
            ok = st.form_submit_button("Lưu tồn kho", use_container_width=True)
        if ok:
            try:
                api_client.post(
                    "/api/data/inventory",
                    json={
                        "product_id": product_id,
                        "region_id": region_id,
                        "on_hand_qty": on_hand,
                        "safety_stock": safety,
                        "incoming_qty": incoming,
                    },
                )
                st.success("Đã cập nhật tồn kho.")
                st.rerun()
            except ApiError as exc:
                auth.handle_api_error(exc)
