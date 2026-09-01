"""Repository interfaces (Protocols).

Keeping these abstract lets us swap the SQLite implementation for a
PostgreSQL one without touching the agents.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Protocol

import aiosqlite

from app.models.crawl_result import CrawlResult
from app.models.faculty import Faculty, ReviewStatus, ValidationStatus
from app.models.institution import Institution
from app.models.page import Page


class InstitutionRepository(Protocol):
    async def upsert(self, conn: aiosqlite.Connection, institution: Institution) -> int:
        """Insert or update; returns the row id."""

    async def get_by_id(
        self, conn: aiosqlite.Connection, institution_id: int
    ) -> Optional[Institution]:
        ...

    async def list_all(
        self, conn: aiosqlite.Connection, *, verified_only: bool = False
    ) -> list[Institution]:
        ...

    async def verify(
        self, conn: aiosqlite.Connection, institution_id: int, *, verified: bool = True
    ) -> None:
        ...


class PageRepository(Protocol):
    async def upsert(self, conn: aiosqlite.Connection, page: Page) -> int:
        ...

    async def get_by_url(
        self, conn: aiosqlite.Connection, url: str
    ) -> Optional[Page]:
        ...

    async def mark_extracted(
        self, conn: aiosqlite.Connection, page_id: int, *, extracted: bool = True
    ) -> None:
        ...

    async def list_pending_extraction(
        self, conn: aiosqlite.Connection
    ) -> list[Page]:
        ...

    async def list_for_institution(
        self, conn: aiosqlite.Connection, institution_id: int
    ) -> list[Page]:
        ...


class FacultyRepository(Protocol):
    async def insert(self, conn: aiosqlite.Connection, faculty: Faculty) -> int:
        ...

    async def update_validation(
        self,
        conn: aiosqlite.Connection,
        faculty_id: int,
        *,
        validation_status: ValidationStatus,
        confidence: float,
        issues: Iterable[str],
        last_validated_at: datetime,
    ) -> None:
        ...

    async def update_review(
        self,
        conn: aiosqlite.Connection,
        faculty_id: int,
        *,
        review_status: ReviewStatus,
    ) -> None:
        ...

    async def update_relevance(
        self, conn: aiosqlite.Connection, faculty_id: int, *, score: float
    ) -> None:
        ...

    async def flag_duplicate(
        self,
        conn: aiosqlite.Connection,
        faculty_id: int,
        *,
        possible_duplicate: bool,
        duplicate_of: Optional[int] = None,
    ) -> None:
        ...

    async def list_all(
        self,
        conn: aiosqlite.Connection,
        *,
        review_status: Optional[ReviewStatus] = None,
        institution_id: Optional[int] = None,
        min_relevance: Optional[float] = None,
    ) -> list[Faculty]:
        ...

    async def get_by_email(
        self, conn: aiosqlite.Connection, email_normalized: str
    ) -> Optional[Faculty]:
        ...

    async def get_by_id(
        self, conn: aiosqlite.Connection, faculty_id: int
    ) -> Optional[Faculty]:
        ...


class CrawlResultRepository(Protocol):
    async def record(self, conn: aiosqlite.Connection, result: CrawlResult) -> None:
        ...


class ExtractionCacheRepository(Protocol):
    async def get(
        self,
        conn: aiosqlite.Connection,
        *,
        content_hash: str,
        prompt_version: str,
        model: str,
    ) -> Optional[str]:
        ...

    async def put(
        self,
        conn: aiosqlite.Connection,
        *,
        content_hash: str,
        prompt_version: str,
        model: str,
        raw_response: str,
        parsed_json: str,
    ) -> None:
        ...


class PipelineStateRepository(Protocol):
    async def get_status(
        self,
        conn: aiosqlite.Connection,
        *,
        run_id: str,
        stage: str,
        entity_type: str,
        entity_id: int,
    ) -> Optional[str]:
        ...

    async def mark(
        self,
        conn: aiosqlite.Connection,
        *,
        run_id: str,
        stage: str,
        entity_type: str,
        entity_id: int,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        ...

    async def reset_run(
        self, conn: aiosqlite.Connection, run_id: str, *, stages: Iterable[str]
    ) -> None:
        ...


__all__ = [
    "InstitutionRepository",
    "PageRepository",
    "FacultyRepository",
    "CrawlResultRepository",
    "ExtractionCacheRepository",
    "PipelineStateRepository",
]
