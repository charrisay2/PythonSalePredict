"""Declarative base + kiểu JSON dùng chung (JSONB trên PostgreSQL, JSON trên SQLite)."""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# JSONB trên PostgreSQL để hỗ trợ index/truy vấn nhanh, JSON trên các DB khác (SQLite)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass
