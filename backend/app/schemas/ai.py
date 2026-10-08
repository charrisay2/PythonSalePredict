"""Pydantic schema cho lớp AI giải thích."""

from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    run_id: int
    question: str | None = Field(default=None, max_length=500)
    language: str = "vi"
    force_refresh: bool = False


class AIReason(BaseModel):
    factor: str
    direction: str = "flat"  # up | down | flat
    magnitude_pct: float = 0.0
    evidence: str = ""


class AIAction(BaseModel):
    action: str
    rationale: str = ""
    priority: str = "medium"  # low | medium | high
    owner: str = ""


class ExplanationOut(BaseModel):
    provider: str
    run_id: int | None = None
    summary: str = ""
    reasons: list[AIReason] = Field(default_factory=list)
    recommended_actions: list[AIAction] = Field(default_factory=list)
    confidence: str = "medium"
    grounded_numbers: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    cached: bool = False
