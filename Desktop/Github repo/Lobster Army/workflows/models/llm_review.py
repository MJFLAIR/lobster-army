from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, ValidationError, field_validator

Decision = Literal["approve", "reject"]


def clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


class LLMReviewResult(BaseModel):
    """
    Hard contract for Phase B.
    LLM must return JSON-only with keys:
      - decision: "approve" | "reject"
      - score: float in [0,1] (clamped)
      - reason: non-empty string
    """
    decision: Decision
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        return clamp01(v)


def safe_parse_llm_review(payload: object) -> tuple[LLMReviewResult | None, str | None]:
    """
    Returns (result, error_msg). Never raises.
    error_msg is a deterministic short string.
    """
    try:
        if not isinstance(payload, dict):
            return None, "payload_not_dict"
        res = LLMReviewResult.model_validate(payload)
        return res, None
    except ValidationError:
        return None, "schema_invalid"
    except Exception:
        return None, "parse_error"
