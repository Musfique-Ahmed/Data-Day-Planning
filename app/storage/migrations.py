"""Schema migrations.

Run as ``CREATE TABLE IF NOT EXISTS`` at startup. No Alembic for the MVP —
the schema is small and we own every migration.
"""

from __future__ import annotations

import aiosqlite


SCHEMA_STATEMENTS: list[str] = [
    # Institutions: a known medical college or university.
    """
    CREATE TABLE IF NOT EXISTS institutions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        website         TEXT NOT NULL,
        country         TEXT NOT NULL DEFAULT 'Bangladesh',
        institution_type TEXT NOT NULL DEFAULT 'medical_college',
        verified        INTEGER NOT NULL DEFAULT 0,
        source_url      TEXT,
        notes           TEXT,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        UNIQUE(website)
    );
    """,
    # Pages: a single crawled page.
    """
    CREATE TABLE IF NOT EXISTS pages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_id  INTEGER REFERENCES institutions(id) ON DELETE CASCADE,
        url             TEXT NOT NULL,
        page_type       TEXT NOT NULL DEFAULT 'unknown',
        http_status     INTEGER,
        crawl_status    TEXT NOT NULL DEFAULT 'ok',
        depth           INTEGER NOT NULL DEFAULT 0,
        content_hash    TEXT,
        extracted       INTEGER NOT NULL DEFAULT 0,
        crawled_at      TEXT NOT NULL,
        error           TEXT,
        UNIQUE(url)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_pages_institution ON pages(institution_id);",
    "CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash);",
    # Faculty: extracted record.
    """
    CREATE TABLE IF NOT EXISTS faculty (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        institution_id    INTEGER REFERENCES institutions(id) ON DELETE SET NULL,
        name              TEXT NOT NULL,
        designation       TEXT,
        department        TEXT,
        institution       TEXT NOT NULL,
        email             TEXT,
        email_raw         TEXT,
        email_normalized  TEXT,
        email_type        TEXT NOT NULL DEFAULT 'unknown',
        research_interest TEXT,
        profile_url       TEXT,
        source_url        TEXT NOT NULL,
        extracted_by      TEXT NOT NULL DEFAULT 'deterministic',
        relevance_score   REAL NOT NULL DEFAULT 0,
        confidence        REAL NOT NULL DEFAULT 0,
        validation_status TEXT NOT NULL DEFAULT 'pending',
        review_status     TEXT NOT NULL DEFAULT 'new',
        possible_duplicate INTEGER NOT NULL DEFAULT 0,
        duplicate_of      INTEGER REFERENCES faculty(id) ON DELETE SET NULL,
        issues            TEXT,
        page_id           INTEGER REFERENCES pages(id) ON DELETE SET NULL,
        scraped_at        TEXT NOT NULL,
        last_validated_at TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_faculty_institution ON faculty(institution_id);",
    "CREATE INDEX IF NOT EXISTS idx_faculty_email ON faculty(email_normalized);",
    "CREATE INDEX IF NOT EXISTS idx_faculty_review ON faculty(review_status);",
    # Outreach: track manual outreach per faculty.
    """
    CREATE TABLE IF NOT EXISTS outreach (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id      INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
        status          TEXT NOT NULL DEFAULT 'new',
        contacted_at    TEXT,
        response        TEXT,
        follow_up_date  TEXT,
        notes           TEXT,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_outreach_faculty ON outreach(faculty_id);",
    # LLM extraction cache.
    """
    CREATE TABLE IF NOT EXISTS extraction_cache (
        content_hash    TEXT NOT NULL,
        prompt_version  TEXT NOT NULL,
        model           TEXT NOT NULL,
        raw_response    TEXT NOT NULL,
        parsed_json     TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        PRIMARY KEY (content_hash, prompt_version, model)
    );
    """,
    # Pipeline state: checkpoints for resume.
    """
    CREATE TABLE IF NOT EXISTS pipeline_state (
        run_id          TEXT NOT NULL,
        stage           TEXT NOT NULL,
        entity_type     TEXT NOT NULL,
        entity_id       INTEGER NOT NULL,
        status          TEXT NOT NULL,
        started_at      TEXT,
        finished_at     TEXT,
        error           TEXT,
        PRIMARY KEY (run_id, stage, entity_type, entity_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_pipeline_state_run ON pipeline_state(run_id);",
    # Runs: top-level run metadata.
    """
    CREATE TABLE IF NOT EXISTS runs (
        id              TEXT PRIMARY KEY,
        started_at      TEXT NOT NULL,
        finished_at     TEXT,
        summary_json    TEXT
    );
    """,
    # Crawl results: append-only record of every URL the crawler fetched.
    # Separate from ``pages`` so HTTP outcomes don't overwrite enriched
    # Page metadata (institution_id, page_type, content_hash, etc.).
    """
    CREATE TABLE IF NOT EXISTS crawl_results (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        url             TEXT NOT NULL,
        final_url       TEXT,
        crawl_status    TEXT NOT NULL DEFAULT 'ok',
        http_status     INTEGER,
        duration_ms     INTEGER NOT NULL DEFAULT 0,
        depth           INTEGER NOT NULL DEFAULT 0,
        page_type       TEXT NOT NULL DEFAULT 'unknown',
        bytes_downloaded INTEGER NOT NULL DEFAULT 0,
        content_hash    TEXT,
        error           TEXT,
        timestamp       TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_crawl_results_url ON crawl_results(url);",
    "CREATE INDEX IF NOT EXISTS idx_crawl_results_status ON crawl_results(crawl_status);",
]


async def ensure_schema(conn: aiosqlite.Connection) -> None:
    """Apply every CREATE statement, idempotently."""

    for stmt in SCHEMA_STATEMENTS:
        await conn.execute(stmt)
    await conn.commit()


__all__ = ["ensure_schema", "SCHEMA_STATEMENTS"]
