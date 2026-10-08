"""Client gọi REST API của backend FastAPI."""

from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

DEFAULT_BASE_URL = "http://localhost:8000"
TIMEOUT = 300


class ApiError(Exception):
    """Lỗi trả về từ API."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_base_url() -> str:
    """Ưu tiên secrets.toml (khi deploy), sau đó biến môi trường, cuối cùng mặc định."""
    try:
        value = st.secrets.get("API_BASE_URL")
        if value:
            return str(value).rstrip("/")
    except Exception:  # noqa: BLE001 - secrets có thể không tồn tại
        pass
    return os.getenv("API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _extract_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:400] or f"HTTP {response.status_code}"
    detail = payload.get("detail", payload)
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("detail") or str(detail)
        errors = detail.get("errors")
        if errors:
            message = f"{message}: " + "; ".join(str(item) for item in errors[:3])
        return message
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict):
                location = ".".join(str(part) for part in item.get("loc", []))
                parts.append(f"{location}: {item.get('msg', '')}")
            else:
                parts.append(str(item))
        return "; ".join(parts)
    return str(detail)


def request(method: str, path: str, *, raw: bool = False, **kwargs) -> Any:
    url = f"{get_base_url()}{path}"
    headers = dict(kwargs.pop("headers", {}) or {})
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs.setdefault("timeout", TIMEOUT)

    try:
        response = requests.request(method, url, headers=headers, **kwargs)
    except requests.exceptions.ConnectionError as exc:
        raise ApiError(
            f"Không kết nối được API tại {get_base_url()}. Hãy kiểm tra backend đã chạy chưa."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise ApiError("Yêu cầu quá thời gian chờ. Hãy thử lại.") from exc

    if response.status_code == 401:
        st.session_state.pop("token", None)
        st.session_state.pop("user", None)
        raise ApiError("Phiên đăng nhập đã hết hạn, hãy đăng nhập lại.", 401)

    if response.status_code >= 400:
        raise ApiError(_extract_detail(response), response.status_code)

    if raw:
        return response.content

    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return response.json()
    return response.content


def get(path: str, params: dict | None = None, raw: bool = False) -> Any:
    return request("GET", path, params=params, raw=raw)


def post(path: str, json: dict | None = None, params: dict | None = None, raw: bool = False) -> Any:
    return request("POST", path, json=json, params=params, raw=raw)


def patch(path: str, json: dict | None = None) -> Any:
    return request("PATCH", path, json=json)


def delete(path: str, params: dict | None = None) -> Any:
    return request("DELETE", path, params=params)


def upload(path: str, file_name: str, content: bytes) -> Any:
    files = {"file": (file_name, content, "text/csv")}
    return request("POST", path, files=files)


def health() -> dict | None:
    try:
        return request("GET", "/health")
    except ApiError:
        return None
