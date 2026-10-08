"""Điểm vào của FastAPI: đăng ký router, CORS, khởi tạo CSDL."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import ai, alerts, auth, dashboard, data, forecast, reports, scenario, users
from app.core.config import settings
from app.db.init_db import init as init_database
from app.schemas.common import HealthOut

logger = logging.getLogger("app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_database()
        logger.info("CSDL đã sẵn sàng (database_url=%s)", settings.resolve_database_url().split("@")[-1])
    except Exception as exc:  # noqa: BLE001
        logger.error("Không khởi tạo được CSDL: %s", exc)
    yield


DESCRIPTION = """
Nền tảng dự báo nhu cầu bán hàng có AI giải thích kế hoạch.

* Huấn luyện nhiều mô hình time-series (Prophet, scikit-learn, baseline, SARIMA)
* So sánh sai số giữa các mô hình (MAPE, sMAPE, RMSE, MAE, Bias)
* AI giải thích lý do nhu cầu tăng/giảm và gợi ý hành động (chỉ dựa trên số liệu đã tính)
* Scenario planning (what-if), cảnh báo rủi ro mất hàng, xuất báo cáo Excel/PDF
"""

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.streamlit\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    users.router,
    data.router,
    forecast.router,
    scenario.router,
    alerts.router,
    reports.router,
    ai.router,
    dashboard.router,
):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/", tags=["Hệ thống"], summary="Thông tin dịch vụ")
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
    }


@app.get("/health", response_model=HealthOut, tags=["Hệ thống"], summary="Kiểm tra tình trạng")
def health() -> HealthOut:
    database = "sqlite" if settings.is_sqlite else "postgresql"
    return HealthOut(
        status="ok",
        app_name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        database=database,
        llm_enabled=settings.llm_enabled,
    )
