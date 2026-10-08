"""Schema dùng chung."""

from pydantic import BaseModel


class Message(BaseModel):
    message: str
    detail: str | None = None


class HealthOut(BaseModel):
    status: str
    app_name: str
    version: str
    environment: str
    database: str
    llm_enabled: bool
