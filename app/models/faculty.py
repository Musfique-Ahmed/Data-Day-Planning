"""Faculty record — the central output of the pipeline.

A faculty record carries provenance fields (``source_url``, ``scraped_at``,
``extracted_by``, ``confidence``) so a human reviewer can always trace a
record back to its origin.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator


class ValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    NEEDS_REVIEW = "needs_review"
    INVALID = "invalid"


class ReviewStatus(str, Enum):
    NEW = "new"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class EmailType(str, Enum):
    INSTITUTIONAL = "institutional"
    PERSONAL = "personal"  # Generic webmail
    UNKNOWN = "unknown"


class ExtractedBy(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    HYBRID = "hybrid"  # Both: deterministic started, LLM refined


class Faculty(BaseModel):
    """A single faculty / academic-staff member record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # --- Identity ------------------------------------------------------------
    id: Optional[int] = None
    institution_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=300)
    designation: Optional[str] = Field(default=None, max_length=200)
    department: Optional[str] = Field(default=None, max_length=200)
    institution: str = Field(min_length=1, max_length=300)

    # --- Contact (publicly displayed only) ----------------------------------
    email: Optional[EmailStr] = None
    email_raw: Optional[str] = None
    email_normalized: Optional[str] = None
    email_type: EmailType = EmailType.UNKNOWN

    # --- Research / profile --------------------------------------------------
    research_interest: list[str] = Field(default_factory=list)
    profile_url: Optional[HttpUrl] = None
    source_url: HttpUrl

    # --- Provenance & scoring ------------------------------------------------
    extracted_by: ExtractedBy = ExtractedBy.DETERMINISTIC
    relevance_score: float = 0.0
    confidence: float = 0.0
    validation_status: ValidationStatus = ValidationStatus.PENDING
    review_status: ReviewStatus = ReviewStatus.NEW

    # --- Quality flags -------------------------------------------------------
    possible_duplicate: bool = False
    duplicate_of: Optional[int] = None
    issues: list[str] = Field(default_factory=list)

    # --- Audit ---------------------------------------------------------------
    page_id: Optional[int] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_validated_at: Optional[datetime] = None

    # --- Validators ----------------------------------------------------------
    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        if v < 0:
            return 0.0
        if v > 1:
            return 1.0
        return float(v)

    @field_validator("relevance_score")
    @classmethod
    def _clamp_relevance(cls, v: float) -> float:
        if v < 0:
            return 0.0
        if v > 100:
            return 100.0
        return float(v)

    @field_validator("research_interest", mode="before")
    @classmethod
    def _split_research_interest(cls, v: Any) -> list[str]:
        """Accept either a list or a comma-/semicolon-separated string."""

        if v is None:
            return []
        if isinstance(v, str):
            return [p.strip() for p in re_split(v) if p.strip()]
        if isinstance(v, list):
            return [str(p).strip() for p in v if str(p).strip()]
        return [str(v)]


class FacultyDraft(BaseModel):
    """Internal record used by the LLM extractor.

    Lighter weight than :class:`Faculty` — ``source_url`` is added by the
    orchestration layer after the LLM returns.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    institution: Optional[str] = None
    email: Optional[str] = None
    research_interest: list[str] = Field(default_factory=list)

    @field_validator("research_interest", mode="before")
    @classmethod
    def _split_research_interest(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [p.strip() for p in re_split(v) if p.strip()]
        if isinstance(v, list):
            return [str(p).strip() for p in v if str(p).strip()]
        return [str(v)]


def re_split(value: str) -> list[str]:
    """Split a research-interest string on commas / semicolons / newlines."""

    return re.split(r"[,;\n]+", value)


__all__ = [
    "Faculty",
    "FacultyDraft",
    "ValidationStatus",
    "ReviewStatus",
    "EmailType",
    "ExtractedBy",
]
