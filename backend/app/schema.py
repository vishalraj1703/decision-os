"""The contract between the AI and the system (spec 5.2), enforced with Pydantic.

Every field is required. "UNKNOWN" is the only allowed value for anything the notes do
not state. Unknown keys from the model are dropped, never trusted.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

UNKNOWN = "UNKNOWN"


class AIModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _clean_missing(v: list[str]) -> list[str]:
    out = []
    for x in v or []:
        x = str(x).strip().lower().replace(" ", "_")
        if x and x not in out:
            out.append(x)
    return out


def _unknownify(v: object) -> str:
    s = "" if v is None else str(v).strip()
    if s.lower() in ("", "unknown", "none", "null", "n/a", "na", "not stated", "unclear", "tbd", "-"):
        return UNKNOWN
    return s


class _Item(AIModel):
    """Shared fields: owner, deadline, evidence, confidence, missing_info."""

    owner: str = UNKNOWN
    deadline: str = UNKNOWN
    evidence_quote: str = Field(min_length=1, max_length=600)
    confidence: float = Field(default=0.5, ge=0, le=1)
    missing_info: list[str] = Field(default_factory=list)

    @field_validator("owner", "deadline", mode="before")
    @classmethod
    def unknownify(cls, v):
        return _unknownify(v)

    @field_validator("missing_info", mode="before")
    @classmethod
    def clean_missing(cls, v):
        return _clean_missing(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.5
        if f > 1 and f <= 100:  # models sometimes answer in percent
            f = f / 100
        return min(1.0, max(0.0, f))


class AIDecision(_Item):
    decision: str = Field(min_length=1, max_length=300)


class AIAction(_Item):
    id: str = Field(pattern=r"^a\d{1,3}$")
    task: str = Field(min_length=1, max_length=300)
    dependencies: list[str] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def norm_id(cls, v):
        return str(v).strip().lower()

    @field_validator("dependencies", mode="before")
    @classmethod
    def norm_deps(cls, v):
        return [str(x).strip().lower() for x in (v or []) if str(x).strip()]


class AIRisk(_Item):
    risk: str = Field(min_length=1, max_length=300)
    severity: Literal["high", "medium", "low", "UNKNOWN"] = UNKNOWN

    @field_validator("severity", mode="before")
    @classmethod
    def norm_severity(cls, v):
        s = str(v or "").strip().lower()
        return s if s in ("high", "medium", "low") else UNKNOWN


class AIContradiction(AIModel):
    topic: str = Field(min_length=1, max_length=120)
    current: str = Field(min_length=1, max_length=200)
    previous: str = Field(min_length=1, max_length=200)
    previous_evidence: str = Field(min_length=1, max_length=600)
    current_evidence: str = Field(min_length=1, max_length=600)


class AIExtraction(AIModel):
    meeting_topic: str = Field(min_length=1, max_length=120)
    decisions: list[AIDecision] = Field(default_factory=list, max_length=30)
    actions: list[AIAction] = Field(default_factory=list, max_length=40)
    risks: list[AIRisk] = Field(default_factory=list, max_length=30)
    contradictions: list[AIContradiction] = Field(default_factory=list, max_length=20)


class AIConflictCheck(AIModel):
    """Reply of the cross-meeting comparison call."""

    contradicts: bool
    topic: str = Field(default="", max_length=120)
    explanation: str = Field(default="", max_length=300)
