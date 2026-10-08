"""Lớp AI giải thích kết quả dự báo (có ràng buộc số liệu)."""

from app.ai.explainer import build_context, explain_run, validate_grounding
from app.ai.providers import call_llm, provider_status

__all__ = ["build_context", "explain_run", "validate_grounding", "call_llm", "provider_status"]
