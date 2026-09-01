"""Tests for app.models.crawl_result."""

from __future__ import annotations

from app.models.crawl_result import CrawlResult, CrawlStatus, CrawlYield


def test_depth_field_round_trips() -> None:
    r = CrawlResult(url="https://x.com/foo", depth=3)
    assert r.depth == 3


def test_default_depth_is_zero() -> None:
    r = CrawlResult(url="https://x.com/foo")
    assert r.depth == 0


def test_crawl_yield_is_frozen() -> None:
    import dataclasses

    y = CrawlYield(
        result=CrawlResult(url="https://x.com/", status=CrawlStatus.OK, depth=1),
        links=("https://x.com/a", "https://x.com/b"),
        anchors={"https://x.com/a": "A"},
    )
    assert y.result.depth == 1
    assert y.links == ("https://x.com/a", "https://x.com/b")
    assert y.anchors == {"https://x.com/a": "A"}
    assert dataclasses.is_frozen(y)