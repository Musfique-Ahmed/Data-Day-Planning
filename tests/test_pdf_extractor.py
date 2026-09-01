"""Tests for app.extraction.pdf_extractor."""

from __future__ import annotations

from app.extraction.pdf_extractor import extract_pdf_text


def test_returns_none_for_falsy_source() -> None:
    assert extract_pdf_text("") is None
    assert extract_pdf_text(None) is None  # type: ignore[arg-type]


def test_returns_none_for_missing_file() -> None:
    assert extract_pdf_text("/tmp/does-not-exist-12345.pdf") is None