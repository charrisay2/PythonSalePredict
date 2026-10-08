"""Helper dùng chung cho toàn backend."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

DATE_FMT = "%Y-%m-%d"


def to_iso(value: date | datetime | str) -> str:
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def parse_iso(value: str) -> date:
    return datetime.strptime(value[:10], DATE_FMT).date()


def date_range(start: str, end: str) -> list[str]:
    start_d = parse_iso(start)
    end_d = parse_iso(end)
    days = (end_d - start_d).days
    return [(start_d + timedelta(days=i)).isoformat() for i in range(days + 1)]


def stable_hash(payload: Any) -> str:
    """Hash ổn định cho dict/list bất kể thứ tự key (dùng làm cache key)."""
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def safe_round(value: float | None, digits: int = 2) -> float:
    if value is None:
        return 0.0
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0
