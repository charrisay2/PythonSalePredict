"""Adapter gọi LLM (OpenAI / Anthropic). Không có key -> trả về thất bại để dùng fallback."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class LLMResult:
    ok: bool
    provider: str
    text: str = ""
    error: str | None = None


def _call_openai(system_prompt: str, user_prompt: str) -> LLMResult:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        return LLMResult(ok=True, provider=f"openai:{settings.openai_model}", text=text)
    except Exception as exc:  # noqa: BLE001
        return LLMResult(ok=False, provider="openai", error=str(exc)[:400])


def _call_anthropic(system_prompt: str, user_prompt: str) -> LLMResult:
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_seconds)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1500,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        return LLMResult(ok=True, provider=f"anthropic:{settings.anthropic_model}", text="\n".join(parts))
    except Exception as exc:  # noqa: BLE001
        return LLMResult(ok=False, provider="anthropic", error=str(exc)[:400])


def call_llm(system_prompt: str, user_prompt: str) -> LLMResult:
    provider = (settings.llm_provider or "none").lower()
    if provider == "openai" and settings.openai_api_key:
        return _call_openai(system_prompt, user_prompt)
    if provider == "anthropic" and settings.anthropic_api_key:
        return _call_anthropic(system_prompt, user_prompt)
    return LLMResult(
        ok=False,
        provider="none",
        error="Chưa cấu hình LLM_PROVIDER / API key. Đang dùng giải thích rule-based.",
    )


def provider_status() -> dict:
    return {
        "provider": settings.llm_provider,
        "enabled": settings.llm_enabled,
        "openai_model": settings.openai_model if settings.openai_api_key else None,
        "anthropic_model": settings.anthropic_model if settings.anthropic_api_key else None,
        "fallback": "rule-based",
    }
