"""Tests for app.models.page."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.crawl_result import CrawlStatus
from app.models.page import Page, PageType


def test_default_crawl_status_is_enum_ok() -> None:
    page = Page(url="https://x.com/")
    assert page.crawl_status == CrawlStatus.OK
    assert isinstance(page.crawl_status, CrawlStatus)


def test_assigning_non_enum_string_raises() -> None:
    with pytest.raises(ValidationError):
        Page(url="https://x.com/", crawl_status="oK")  # type: ignore[arg-type]


def test_default_page_type_is_unknown() -> None:
    page = Page(url="https://x.com/")
    assert page.page_type == PageType.UNKNOWN