"""Kiểm thử giao diện: render từng trang Streamlit ở chế độ headless, đảm bảo không phát sinh lỗi.

Cần backend đang chạy (mặc định http://localhost:8000). Nếu không kết nối được, bỏ qua.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.getenv("FIRST_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("FIRST_ADMIN_PASSWORD", "Admin@12345")

PAGES = [
    "pages/1_Dashboard.py",
    "pages/2_Data.py",
    "pages/3_Forecast.py",
    "pages/4_Model_Compare.py",
    "pages/5_Scenario.py",
    "pages/6_Alerts.py",
    "pages/7_AI_Insights.py",
    "pages/8_Reports.py",
    "pages/9_Admin_Users.py",
]


def _backend_available() -> bool:
    import requests

    try:
        return requests.get(f"{API_BASE_URL}/health", timeout=3).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _login() -> tuple[str, dict]:
    import requests

    response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["access_token"], payload["user"]


pytestmark = pytest.mark.skipif(
    not _backend_available(),
    reason=f"Cần backend đang chạy tại {API_BASE_URL}",
)


@pytest.fixture(scope="module")
def session_state() -> dict:
    token, user = _login()
    return {"token": token, "user": user}


@pytest.fixture(scope="module")
def app_test():
    from streamlit.testing.v1 import AppTest

    return AppTest


def test_login_page_renders_without_error(app_test):
    at = app_test.from_file(str(FRONTEND / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_error(app_test, session_state, page):
    at = app_test.from_file(str(FRONTEND / page), default_timeout=180)
    for key, value in session_state.items():
        at.session_state[key] = value
    at.run()
    assert not at.exception, f"{page}: {at.exception}"
