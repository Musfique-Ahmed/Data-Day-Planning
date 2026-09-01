"""Tests for app.utils.normalization.normalize_url."""

from __future__ import annotations

from app.utils.normalization import normalize_url


def test_strips_trailing_slash() -> None:
    assert normalize_url("https://x.com/foo/") == "https://x.com/foo"


def test_strips_fragment() -> None:
    assert normalize_url("https://x.com/foo#frag") == "https://x.com/foo"


def test_lowercases_netloc() -> None:
    assert normalize_url("https://X.COM/foo") == "https://x.com/foo"


def test_keeps_root_slash() -> None:
    assert normalize_url("https://x.com/") == "https://x.com/"


def test_empty_returns_empty() -> None:
    assert normalize_url("") == ""
    assert normalize_url(None) == ""