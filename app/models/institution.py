"""Institution model — a verified medical college or university."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Institution(BaseModel):
    """A candidate medical institution.

    Verification is *whether a human has signed off on it as a real official
    source*. Until then, ``verified`` is ``False``.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: Optional[int] = None
    name: str = Field(min_length=1, max_length=300)
    website: HttpUrl
    country: str = "Bangladesh"
    institution_type: str = "medical_college"
    verified: bool = False
    source_url: Optional[HttpUrl] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["Institution"]