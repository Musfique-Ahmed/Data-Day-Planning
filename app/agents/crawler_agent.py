"""Crawler agent — orchestrates the browser crawl loop and writes pages.

The agent is the *only* place where :class:`app.browser.crawler.Crawler`
meets the storage layer. It also selects which URLs to crawl based on the
:class:`LinkRanker` score and stops at the configured per-domain quota.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

import aiosqlite

from app.browser.crawler import Crawler, CrawlLimits
from app.models.crawl_result import CrawlStatus, CrawlYield
from app.models.page import Page, PageType
from app.storage.sqlite_repository import SQLiteCrawlResultRepository, SQLitePageRepository

_log = logging.getLogger(__name__)


# Tokens that mark a page (or anchor text) as a faculty directory listing.
_FACULTY_DIRECTORY_TOKENS: tuple[str, ...] = (
    "faculty-member",
    "faculty_members",
    "faculty_member",
)


def classify_page(url: str, anchor_lookup: dict[str, str] | None = None) -> PageType:
    """Best-effort page-type classification."""

    blob = (url + " " + " ".join((anchor_lookup or {}).values())).lower()
    if any(k in blob for k in _FACULTY_DIRECTORY_TOKENS):
        return PageType.FACULTY_DIRECTORY
    if "faculty" in blob and ("list" in blob or "members" in blob or "our" in blob):
        return PageType.FACULTY_DIRECTORY
    if "teacher" in blob or "staff" in blob:
        return PageType.STAFF_LIST
    if "department" in blob:
        return PageType.DEPARTMENT
    if blob.endswith(("professor", "dr.", "dr ")):
        return PageType.FACULTY_PROFILE
    return PageType.OTHER


class CrawlerAgent:
    """Owns the Playwright session and writes pages into SQLite.

    The agent assumes the caller has already run ``ensure_schema`` —
    it does not call it on every crawl.
    """

    def __init__(self, *, limits: CrawlLimits | None = None) -> None:
        self._limits = limits or CrawlLimits()

    async def crawl_institution(
        self, *, institution_id: int, start_url: str, manager, conn: aiosqlite.Connection
    ) -> AsyncIterator[Page]:
        """Crawl an institution starting from ``start_url`` and yield persisted Pages."""

        page_repo = SQLitePageRepository()
        crawl_repo = SQLiteCrawlResultRepository()
        crawler = Crawler(manager, limits=self._limits)
        async for yield_ in crawler.crawl(start_url):
            page = self._build_page(institution_id, yield_)
            await page_repo.upsert(conn, page)
            await crawl_repo.record(conn, yield_.result)
            if yield_.result.status == CrawlStatus.OK:
                yield page

    @staticmethod
    def _build_page(institution_id: int, yield_: CrawlYield) -> Page:
        """Map a :class:`CrawlYield` to a persisted :class:`Page`."""

        result = yield_.result
        page_type = classify_page(
            str(result.final_url or result.url), yield_.anchors or None
        )
        return Page(
            institution_id=institution_id,
            url=result.final_url or result.url,
            page_type=page_type,
            http_status=result.http_status,
            crawl_status=result.status,
            depth=result.depth,
            content_hash=result.content_hash,
            crawled_at=result.timestamp,
            error=result.error,
        )


__all__ = ["CrawlerAgent", "Page", "PageType", "classify_page"]
