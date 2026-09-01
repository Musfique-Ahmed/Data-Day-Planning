"""Tests for SQLiteCrawlResultRepository."""

from __future__ import annotations

import aiosqlite
import pytest

from app.models.crawl_result import CrawlResult, CrawlStatus
from app.storage.sqlite_repository import SQLiteCrawlResultRepository

pytestmark = pytest.mark.asyncio


async def test_record_inserts_row(tmp_db: aiosqlite.Connection) -> None:
    repo = SQLiteCrawlResultRepository()
    result = CrawlResult(
        url="https://x.com/foo",
        status=CrawlStatus.OK,
        http_status=200,
        duration_ms=120,
        depth=2,
        page_type="page",
        bytes_downloaded=1024,
        content_hash="abc123",
    )
    await repo.record(tmp_db, result)

    rows = await (
        await tmp_db.execute("SELECT url, crawl_status, depth, http_status FROM crawl_results")
    ).fetchall()
    assert rows == [("https://x.com/foo", "ok", 2, 200)]


async def test_record_does_not_overwrite_pages(tmp_db: aiosqlite.Connection) -> None:
    """B3 regression: record() must write to crawl_results, not pages."""

    repo = SQLiteCrawlResultRepository()
    result = CrawlResult(url="https://x.com/foo", status=CrawlStatus.OK)
    await repo.record(tmp_db, result)

    pages_rows = await (
        await tmp_db.execute("SELECT COUNT(*) FROM pages")
    ).fetchone()
    assert pages_rows[0] == 0