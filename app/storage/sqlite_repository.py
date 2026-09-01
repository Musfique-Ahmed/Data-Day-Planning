"""SQLite-backed implementations of the repository Protocols.

These are thin wrappers around ``aiosqlite`` — every method takes the
connection as its first argument so callers can compose multiple operations
inside a single transaction.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

import aiosqlite

from app.models.crawl_result import CrawlResult
from app.models.faculty import Faculty, ReviewStatus, ValidationStatus
from app.models.institution import Institution
from app.models.page import Page
from app.utils.normalization import normalize_email

_log = logging.getLogger(__name__)


def _now() -> datetime:
    """UTC now — replaces deprecated ``datetime.utcnow()``."""

    return datetime.now(timezone.utc)


def _dt(value: datetime | None) -> Optional[str]:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        _log.warning("unparseable datetime in DB: %r", value)
        return None


class SQLiteInstitutionRepository:
    async def upsert(self, conn: aiosqlite.Connection, institution: Institution) -> int:
        now = _now().isoformat()
        cursor = await conn.execute(
            """
            INSERT INTO institutions
                (name, website, country, institution_type, verified,
                 source_url, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(website) DO UPDATE SET
                name            = excluded.name,
                country         = excluded.country,
                institution_type = excluded.institution_type,
                verified        = institutions.verified,
                source_url      = excluded.source_url,
                notes           = excluded.notes,
                updated_at      = excluded.updated_at
            """,
            (
                institution.name,
                str(institution.website),
                institution.country,
                institution.institution_type,
                1 if institution.verified else 0,
                str(institution.source_url) if institution.source_url else None,
                institution.notes,
                now,
                now,
            ),
        )
        await conn.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        row = await (
            await conn.execute(
                "SELECT id FROM institutions WHERE website = ?",
                (str(institution.website),),
            )
        ).fetchone()
        return row[0] if row else 0

    async def get_by_id(
        self, conn: aiosqlite.Connection, institution_id: int
    ) -> Optional[Institution]:
        row = await (
            await conn.execute(
                "SELECT * FROM institutions WHERE id = ?", (institution_id,)
            )
        ).fetchone()
        return _row_to_institution(row)

    async def list_all(
        self, conn: aiosqlite.Connection, *, verified_only: bool = False
    ) -> list[Institution]:
        sql = "SELECT * FROM institutions"
        args: tuple = ()
        if verified_only:
            sql += " WHERE verified = 1"
        sql += " ORDER BY name"
        rows = await (await conn.execute(sql, args)).fetchall()
        return [r for r in (_row_to_institution(r) for r in rows) if r is not None]

    async def verify(
        self, conn: aiosqlite.Connection, institution_id: int, *, verified: bool = True
    ) -> None:
        await conn.execute(
            "UPDATE institutions SET verified = ?, updated_at = ? WHERE id = ?",
            (1 if verified else 0, _now().isoformat(), institution_id),
        )
        await conn.commit()


def _row_to_institution(row: aiosqlite.Row | tuple | None) -> Optional[Institution]:
    if row is None:
        return None
    keys = (
        "id",
        "name",
        "website",
        "country",
        "institution_type",
        "verified",
        "source_url",
        "notes",
        "created_at",
        "updated_at",
    )
    record = dict(zip(keys, row, strict=False))
    return Institution(
        id=record["id"],
        name=record["name"],
        website=record["website"],
        country=record["country"],
        institution_type=record["institution_type"],
        verified=bool(record["verified"]),
        source_url=record["source_url"],
        notes=record["notes"],
        created_at=_parse_dt(record["created_at"]) or _now(),
        updated_at=_parse_dt(record["updated_at"]) or _now(),
    )


class SQLitePageRepository:
    async def upsert(self, conn: aiosqlite.Connection, page: Page) -> int:
        await conn.execute(
            """
            INSERT INTO pages
                (institution_id, url, page_type, http_status, crawl_status,
                 depth, content_hash, extracted, crawled_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                institution_id = excluded.institution_id,
                page_type      = excluded.page_type,
                http_status    = excluded.http_status,
                crawl_status   = excluded.crawl_status,
                depth          = excluded.depth,
                content_hash   = excluded.content_hash,
                crawled_at     = excluded.crawled_at,
                error          = excluded.error
            """,
            (
                page.institution_id,
                str(page.url),
                page.page_type.value if hasattr(page.page_type, "value") else str(page.page_type),
                page.http_status,
                page.crawl_status.value,
                page.depth,
                page.content_hash,
                1 if page.extracted else 0,
                _dt(page.crawled_at),
                page.error,
            ),
        )
        await conn.commit()
        row = await (
            await conn.execute("SELECT id FROM pages WHERE url = ?", (str(page.url),))
        ).fetchone()
        return row[0] if row else 0

    async def get_by_url(
        self, conn: aiosqlite.Connection, url: str
    ) -> Optional[Page]:
        row = await (
            await conn.execute("SELECT * FROM pages WHERE url = ?", (url,))
        ).fetchone()
        return _row_to_page(row)

    async def mark_extracted(
        self, conn: aiosqlite.Connection, page_id: int, *, extracted: bool = True
    ) -> None:
        await conn.execute(
            "UPDATE pages SET extracted = ? WHERE id = ?",
            (1 if extracted else 0, page_id),
        )
        await conn.commit()

    async def list_pending_extraction(
        self, conn: aiosqlite.Connection
    ) -> list[Page]:
        rows = await (
            await conn.execute(
                "SELECT * FROM pages WHERE extracted = 0 AND crawl_status = 'ok'"
                " ORDER BY id"
            )
        ).fetchall()
        return [p for p in (_row_to_page(r) for r in rows) if p is not None]

    async def list_for_institution(
        self, conn: aiosqlite.Connection, institution_id: int
    ) -> list[Page]:
        rows = await (
            await conn.execute(
                "SELECT * FROM pages WHERE institution_id = ? ORDER BY id",
                (institution_id,),
            )
        ).fetchall()
        return [p for p in (_row_to_page(r) for r in rows) if p is not None]


def _row_to_page(row: aiosqlite.Row | tuple | None) -> Optional[Page]:
    if row is None:
        return None
    keys = (
        "id",
        "institution_id",
        "url",
        "page_type",
        "http_status",
        "crawl_status",
        "depth",
        "content_hash",
        "extracted",
        "crawled_at",
        "error",
    )
    record = dict(zip(keys, row, strict=False))
    from app.models.crawl_result import CrawlStatus
    from app.models.page import PageType

    try:
        pt = PageType(record["page_type"])
    except ValueError:
        pt = PageType.UNKNOWN
    try:
        cs = CrawlStatus(record["crawl_status"])
    except ValueError:
        cs = CrawlStatus.OK
    return Page(
        id=record["id"],
        institution_id=record["institution_id"],
        url=record["url"],
        page_type=pt,
        http_status=record["http_status"],
        crawl_status=cs,
        depth=record["depth"],
        content_hash=record["content_hash"],
        extracted=bool(record["extracted"]),
        crawled_at=_parse_dt(record["crawled_at"]) or _now(),
        error=record["error"],
    )


class SQLiteFacultyRepository:
    async def insert(self, conn: aiosqlite.Connection, faculty: Faculty) -> int:
        research = json.dumps(faculty.research_interest, ensure_ascii=False)
        issues = json.dumps(faculty.issues, ensure_ascii=False)
        cursor = await conn.execute(
            """
            INSERT INTO faculty
                (institution_id, name, designation, department, institution,
                 email, email_raw, email_normalized, email_type,
                 research_interest, profile_url, source_url,
                 extracted_by, relevance_score, confidence,
                 validation_status, review_status,
                 possible_duplicate, duplicate_of, issues,
                 page_id, scraped_at, last_validated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                faculty.institution_id,
                faculty.name,
                faculty.designation,
                faculty.department,
                faculty.institution,
                faculty.email,
                faculty.email_raw,
                faculty.email_normalized
                or (normalize_email(faculty.email) if faculty.email else None),
                faculty.email_type.value,
                research,
                str(faculty.profile_url) if faculty.profile_url else None,
                str(faculty.source_url),
                faculty.extracted_by.value,
                faculty.relevance_score,
                faculty.confidence,
                faculty.validation_status.value,
                faculty.review_status.value,
                1 if faculty.possible_duplicate else 0,
                faculty.duplicate_of,
                issues,
                faculty.page_id,
                _dt(faculty.scraped_at),
                _dt(faculty.last_validated_at),
            ),
        )
        await conn.commit()
        return cursor.lastrowid or 0

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
        await conn.execute(
            """
            UPDATE faculty SET
                validation_status = ?,
                confidence = ?,
                issues = ?,
                last_validated_at = ?
            WHERE id = ?
            """,
            (
                validation_status.value,
                confidence,
                json.dumps(list(issues), ensure_ascii=False),
                _dt(last_validated_at),
                faculty_id,
            ),
        )
        await conn.commit()

    async def update_review(
        self,
        conn: aiosqlite.Connection,
        faculty_id: int,
        *,
        review_status: ReviewStatus,
    ) -> None:
        await conn.execute(
            "UPDATE faculty SET review_status = ? WHERE id = ?",
            (review_status.value, faculty_id),
        )
        await conn.commit()

    async def update_relevance(
        self, conn: aiosqlite.Connection, faculty_id: int, *, score: float
    ) -> None:
        await conn.execute(
            "UPDATE faculty SET relevance_score = ? WHERE id = ?",
            (score, faculty_id),
        )
        await conn.commit()

    async def flag_duplicate(
        self,
        conn: aiosqlite.Connection,
        faculty_id: int,
        *,
        possible_duplicate: bool,
        duplicate_of: Optional[int] = None,
    ) -> None:
        await conn.execute(
            "UPDATE faculty SET possible_duplicate = ?, duplicate_of = ? WHERE id = ?",
            (1 if possible_duplicate else 0, duplicate_of, faculty_id),
        )
        await conn.commit()

    async def list_all(
        self,
        conn: aiosqlite.Connection,
        *,
        review_status: Optional[ReviewStatus] = None,
        institution_id: Optional[int] = None,
        min_relevance: Optional[float] = None,
    ) -> list[Faculty]:
        clauses: list[str] = []
        args: list = []
        if review_status is not None:
            clauses.append("review_status = ?")
            args.append(review_status.value)
        if institution_id is not None:
            clauses.append("institution_id = ?")
            args.append(institution_id)
        if min_relevance is not None:
            clauses.append("relevance_score >= ?")
            args.append(min_relevance)
        sql = "SELECT * FROM faculty"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY relevance_score DESC, confidence DESC, id"
        rows = await (await conn.execute(sql, tuple(args))).fetchall()
        return [f for f in (_row_to_faculty(r) for r in rows) if f is not None]

    async def get_by_email(
        self, conn: aiosqlite.Connection, email_normalized: str
    ) -> Optional[Faculty]:
        row = await (
            await conn.execute(
                "SELECT * FROM faculty WHERE email_normalized = ? LIMIT 1",
                (email_normalized,),
            )
        ).fetchone()
        return _row_to_faculty(row)

    async def get_by_id(
        self, conn: aiosqlite.Connection, faculty_id: int
    ) -> Optional[Faculty]:
        row = await (
            await conn.execute("SELECT * FROM faculty WHERE id = ?", (faculty_id,))
        ).fetchone()
        return _row_to_faculty(row)


def _row_to_faculty(row: aiosqlite.Row | tuple | None) -> Optional[Faculty]:
    if row is None:
        return None
    keys = (
        "id",
        "institution_id",
        "name",
        "designation",
        "department",
        "institution",
        "email",
        "email_raw",
        "email_normalized",
        "email_type",
        "research_interest",
        "profile_url",
        "source_url",
        "extracted_by",
        "relevance_score",
        "confidence",
        "validation_status",
        "review_status",
        "possible_duplicate",
        "duplicate_of",
        "issues",
        "page_id",
        "scraped_at",
        "last_validated_at",
    )
    record = dict(zip(keys, row, strict=False))

    research_raw = record["research_interest"]
    try:
        research = json.loads(research_raw) if research_raw else []
    except json.JSONDecodeError:
        research = [s for s in (research_raw or "").split("|") if s]

    issues_raw = record["issues"]
    try:
        issues = json.loads(issues_raw) if issues_raw else []
    except json.JSONDecodeError:
        issues = [issues_raw] if issues_raw else []

    from app.models.faculty import EmailType, ExtractedBy, ReviewStatus, ValidationStatus

    try:
        et = EmailType(record["email_type"])
    except ValueError:
        et = EmailType.UNKNOWN
    try:
        eb = ExtractedBy(record["extracted_by"])
    except ValueError:
        eb = ExtractedBy.DETERMINISTIC
    try:
        vs = ValidationStatus(record["validation_status"])
    except ValueError:
        vs = ValidationStatus.PENDING
    try:
        rs = ReviewStatus(record["review_status"])
    except ValueError:
        rs = ReviewStatus.NEW

    return Faculty(
        id=record["id"],
        institution_id=record["institution_id"],
        name=record["name"],
        designation=record["designation"],
        department=record["department"],
        institution=record["institution"],
        email=record["email"],
        email_raw=record["email_raw"],
        email_normalized=record["email_normalized"] or normalize_email(record["email"]),
        email_type=et,
        research_interest=research,
        profile_url=record["profile_url"],
        source_url=record["source_url"],
        extracted_by=eb,
        relevance_score=record["relevance_score"] or 0.0,
        confidence=record["confidence"] or 0.0,
        validation_status=vs,
        review_status=rs,
        possible_duplicate=bool(record["possible_duplicate"]),
        duplicate_of=record["duplicate_of"],
        issues=issues,
        page_id=record["page_id"],
        scraped_at=_parse_dt(record["scraped_at"]) or _now(),
        last_validated_at=_parse_dt(record["last_validated_at"]),
    )


class SQLiteCrawlResultRepository:
    async def record(self, conn: aiosqlite.Connection, result: CrawlResult) -> None:
        """Append a crawl-result row to the dedicated ``crawl_results`` table."""

        await conn.execute(
            """
            INSERT INTO crawl_results
                (url, final_url, crawl_status, http_status,
                 duration_ms, depth, page_type, bytes_downloaded,
                 content_hash, error, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(result.url),
                str(result.final_url) if result.final_url else None,
                result.status.value,
                result.http_status,
                result.duration_ms,
                result.depth,
                result.page_type,
                result.bytes_downloaded,
                result.content_hash,
                result.error,
                _dt(result.timestamp),
            ),
        )
        await conn.commit()


class SQLiteExtractionCacheRepository:
    async def get(
        self,
        conn: aiosqlite.Connection,
        *,
        content_hash: str,
        prompt_version: str,
        model: str,
    ) -> Optional[str]:
        row = await (
            await conn.execute(
                """
                SELECT parsed_json FROM extraction_cache
                WHERE content_hash = ? AND prompt_version = ? AND model = ?
                """,
                (content_hash, prompt_version, model),
            )
        ).fetchone()
        return row[0] if row else None

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
        await conn.execute(
            """
            INSERT OR REPLACE INTO extraction_cache
                (content_hash, prompt_version, model, raw_response, parsed_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                content_hash,
                prompt_version,
                model,
                raw_response,
                parsed_json,
                _now().isoformat(),
            ),
        )
        await conn.commit()


class SQLitePipelineStateRepository:
    async def get_status(
        self,
        conn: aiosqlite.Connection,
        *,
        run_id: str,
        stage: str,
        entity_type: str,
        entity_id: int,
    ) -> Optional[str]:
        row = await (
            await conn.execute(
                """
                SELECT status FROM pipeline_state
                WHERE run_id = ? AND stage = ? AND entity_type = ? AND entity_id = ?
                """,
                (run_id, stage, entity_type, entity_id),
            )
        ).fetchone()
        return row[0] if row else None

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
        now = _now().isoformat()
        started_at = now if status == "running" else None
        finished_at = now if status in {"done", "failed", "skipped"} else None
        await conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_state
                (run_id, stage, entity_type, entity_id, status,
                 started_at, finished_at, error)
            VALUES (?, ?, ?, ?, ?, COALESCE(?, started_at), COALESCE(?, finished_at), ?)
            """,
            (
                run_id,
                stage,
                entity_type,
                entity_id,
                status,
                started_at,
                finished_at,
                error,
            ),
        )
        await conn.commit()

    async def reset_run(
        self, conn: aiosqlite.Connection, run_id: str, *, stages: Iterable[str]
    ) -> None:
        stage_list = list(stages)
        if not stage_list:
            return
        placeholders = ",".join("?" for _ in stage_list)
        await conn.execute(
            f"DELETE FROM pipeline_state WHERE run_id = ? AND stage IN ({placeholders})",
            (run_id, *stage_list),
        )
        await conn.commit()


__all__ = [
    "SQLiteInstitutionRepository",
    "SQLitePageRepository",
    "SQLiteFacultyRepository",
    "SQLiteCrawlResultRepository",
    "SQLiteExtractionCacheRepository",
    "SQLitePipelineStateRepository",
]
