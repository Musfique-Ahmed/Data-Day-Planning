"""The result of a single crawl attempt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CrawlStatus(str, Enum):
    OK = "ok"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    SKIPPED = "skipped"


class CrawlResult(BaseModel):
    """Captures everything the crawler observed on one URL."""

    model_config = ConfigDict(str_strip_whitespace=True)

    url: HttpUrl
    final_url: Optional[HttpUrl] = None
    status: CrawlStatus = CrawlStatus.OK
    http_status: Optional[int] = None
    duration_ms: int = 0
    depth: int = 0
    page_type: str = "unknown"
    error: Optional[str] = None
    content_hash: Optional[str] = None
    bytes_downloaded: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class CrawlYield:
    """Sidecar envelope yielded by :class:`Crawler`.

    Keeps :class:`CrawlResult` a clean DTO while letting the crawler pass
    transient orchestration data (``links`` to enqueue, ``anchors`` for
    page-type classification) alongside it.
    """

    result: CrawlResult
    links: tuple[str, ...] = ()
    anchors: dict[str, str] = field(default_factory=dict)


__all__ = ["CrawlResult", "CrawlStatus", "CrawlYield"]