"""A page we have stored in the crawl index."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.crawl_result import CrawlStatus


class PageType(str, Enum):
    UNKNOWN = "unknown"
    HOMEPAGE = "homepage"
    FACULTY_DIRECTORY = "faculty_directory"
    FACULTY_PROFILE = "faculty_profile"
    DEPARTMENT = "department"
    STAFF_LIST = "staff_list"
    TEACHERS = "teachers"
    OTHER = "other"


class Page(BaseModel):
    """A page persisted in the SQLite ``pages`` table."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: Optional[int] = None
    institution_id: Optional[int] = None
    url: HttpUrl
    page_type: PageType = PageType.UNKNOWN
    http_status: Optional[int] = None
    crawl_status: CrawlStatus = CrawlStatus.OK
    depth: int = 0
    content_hash: Optional[str] = None
    extracted: bool = False
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


__all__ = ["Page", "PageType"]