"""Cấu hình chung cho pytest: dùng CSDL SQLite riêng và tắt LLM."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

TEST_DB = ROOT / "test_demand_forecast.db"

# Biến môi trường có độ ưu tiên cao hơn file .env -> sẽ ghi đè cấu hình dev
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SECRET_KEY"] = "pytest-secret-key-please-change-32chars"
os.environ["LLM_PROVIDER"] = "none"
os.environ["FIRST_ADMIN_EMAIL"] = "admin@example.com"
os.environ["FIRST_ADMIN_PASSWORD"] = "Admin@12345"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    import app.models  # noqa: F401  (đăng ký metadata)
    from app.db.base import Base
    from app.db.init_db import bootstrap_admin, create_tables
    from app.db.session import engine
    from app.main import app

    # Làm sạch schema thay vì xóa file (tránh vấn đề quyền file)
    Base.metadata.drop_all(bind=engine)
    create_tables()
    bootstrap_admin()

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "Admin@12345"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def seeded_data(client: TestClient, auth_headers: dict) -> dict:
    response = client.post(
        "/api/data/generate-sample",
        headers=auth_headers,
        json={"days": 240, "products": 3, "regions": 2, "channels": 2, "seed": 7, "reset": True},
    )
    assert response.status_code == 200, response.text
    return response.json()
