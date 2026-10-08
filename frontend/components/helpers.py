"""Helper dùng chung cho các trang Streamlit."""

from __future__ import annotations

import time

import streamlit as st

from components import api_client
from components.api_client import ApiError

TERMINAL_STATUSES = {"completed", "failed"}


def poll_run(run_id: int, timeout_seconds: int = 900, interval: float = 2.5) -> dict:
    """Chờ đến khi lần dự báo kết thúc, hiển thị tiến trình."""
    progress = st.progress(0.0, text="Đang huấn luyện mô hình...")
    started = time.time()
    while True:
        run = api_client.get(f"/api/forecast/runs/{run_id}")
        status = run.get("status")
        elapsed = time.time() - started
        if status in TERMINAL_STATUSES:
            progress.progress(1.0, text=f"Hoàn tất sau {elapsed:.0f} giây")
            time.sleep(0.4)
            progress.empty()
            return run
        progress.progress(min(0.95, elapsed / max(timeout_seconds, 1)), text=f"Trạng thái: {status} ({elapsed:.0f}s)")
        if elapsed > timeout_seconds:
            progress.empty()
            raise ApiError(f"Quá thời gian chờ ({timeout_seconds}s). Lần dự báo vẫn đang chạy ở backend.")
        time.sleep(interval)


def load_catalog() -> dict:
    """Tải danh mục sản phẩm / khu vực / kênh bán."""
    return {
        "products": api_client.get("/api/data/products"),
        "regions": api_client.get("/api/data/regions"),
        "channels": api_client.get("/api/data/channels"),
    }


def scope_selector(catalog: dict, key_prefix: str = "scope") -> dict:
    """Bộ chọn phạm vi dự báo (sản phẩm / khu vực / kênh)."""
    columns = st.columns(3)
    with columns[0]:
        product_ids = st.multiselect(
            "Sản phẩm",
            options=[item["id"] for item in catalog["products"]],
            format_func=lambda value: next(
                (f"{item['sku']} - {item['name']}" for item in catalog["products"] if item["id"] == value),
                str(value),
            ),
            key=f"{key_prefix}_products",
            placeholder="Tất cả sản phẩm",
        )
    with columns[1]:
        region_ids = st.multiselect(
            "Khu vực",
            options=[item["id"] for item in catalog["regions"]],
            format_func=lambda value: next(
                (item["name"] for item in catalog["regions"] if item["id"] == value), str(value)
            ),
            key=f"{key_prefix}_regions",
            placeholder="Tất cả khu vực",
        )
    with columns[2]:
        channel_ids = st.multiselect(
            "Kênh bán",
            options=[item["id"] for item in catalog["channels"]],
            format_func=lambda value: next(
                (item["name"] for item in catalog["channels"] if item["id"] == value), str(value)
            ),
            key=f"{key_prefix}_channels",
            placeholder="Tất cả kênh",
        )
    return {
        "product_ids": product_ids or None,
        "region_ids": region_ids or None,
        "channel_ids": channel_ids or None,
    }


def load_models() -> list[dict]:
    return api_client.get("/api/forecast/models")


def load_runs(limit: int = 30, only_completed: bool = False) -> list[dict]:
    runs = api_client.get("/api/forecast/runs", params={"limit": limit})
    if only_completed:
        runs = [run for run in runs if run.get("status") == "completed"]
    return runs


def run_label(run: dict) -> str:
    return f"#{run['id']} · {run['name']} · {run['granularity']} · {run['horizon']} ngày"


def require_data_available(stats: dict) -> bool:
    if stats.get("total_rows", 0) <= 0:
        st.warning(
            "Chưa có dữ liệu bán hàng. Hãy vào trang **Dữ liệu** để nạp CSV hoặc sinh dữ liệu mẫu trước."
        )
        return False
    return True
