"""Cấu hình trung tâm của backend (đọc từ biến môi trường / file .env)."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Thư mục gốc dự án (chứa .env) - backend/app/core/config.py -> parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILES = (str(PROJECT_ROOT / ".env"), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- App ---
    app_name: str = "Demand Forecasting Platform"
    environment: str = "development"
    api_prefix: str = "/api"
    version: str = "1.0.0"

    # --- Security ---
    secret_key: str = "dev-secret-change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # --- Database ---
    database_url: str = "sqlite:///./demand_forecast.db"

    # --- CORS (danh sách origin phân cách bằng dấu phẩy) ---
    backend_cors_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    # --- Bootstrap admin ---
    first_admin_email: str = "admin@example.com"
    first_admin_password: str = "Admin@12345"
    first_admin_name: str = "System Administrator"

    # --- LLM ---
    llm_provider: str = "none"  # none | openai | anthropic
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    llm_timeout_seconds: int = 45

    @property
    def cors_origins(self) -> List[str]:
        return [item.strip() for item in self.backend_cors_origins.split(",") if item.strip()]

    def resolve_database_url(self) -> str:
        """Chuẩn hóa đường dẫn SQLite tương đối theo gốc dự án (tránh lệch theo CWD)."""
        url = self.database_url
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            return url

        raw_path = url[len(prefix) :]
        if raw_path.startswith(":"):  # ví dụ sqlite:///:memory:
            return url
        if raw_path.startswith("./"):
            raw_path = raw_path[2:]

        path = Path(raw_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return f"{prefix}{path.as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
