"""Tests for the obfuscation decoder."""

from __future__ import annotations

from app.extraction.email_extractor import EmailExtractor


def test_decode_brackets() -> None:
    assert (
        EmailExtractor._decode_obfuscated("name [at] domain [dot] tld")
        == "name@domain.tld"
    )


def test_decode_parens() -> None:
    assert (
        EmailExtractor._decode_obfuscated("name(at)domain(dot)tld")
        == "name@domain.tld"
    )


def test_decode_braces() -> None:
    assert (
        EmailExtractor._decode_obfuscated("name{at}domain{dot}tld")
        == "name@domain.tld"
    )


def test_decode_spaced_words() -> None:
    assert (
        EmailExtractor._decode_obfuscated("name at domain dot tld")
        == "name@domain.tld"
    )


def test_decode_returns_none_for_empty() -> None:
    assert EmailExtractor._decode_obfuscated("") is None