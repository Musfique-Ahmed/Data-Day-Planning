"""String / email / name normalization.

Normalization is intentionally conservative — we never *modify* the canonical
name or email stored on a record. We only produce comparison-friendly
variants. Original values are preserved in ``email_raw`` / the raw record.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable
from urllib.parse import urlparse

_WHITESPACE_RE = _LEADING_TRAILING_WS_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse internal whitespace and trim the input."""

    return _WHITESPACE_RE.sub(" ", text or "").strip()


# Common Bangladeshi / academic honorifics and titles that should be removed
# before comparing names for deduplication.
_TITLE_PREFIXES = (
    "professor",
    "prof.",
    "prof",
    "dr.",
    "dr",
    "doctor",
    "mr.",
    "mr",
    "mrs.",
    "mrs",
    "ms.",
    "ms",
    "miss",
    "md.",
    "md",
)
_TITLE_PATTERN = re.compile(
    r"^(?:" + "|".join(re.escape(t) for t in _TITLE_PREFIXES) + r")\s+",
    flags=re.IGNORECASE,
)
_BANGLA_TITLE_PATTERN = re.compile(r"^(?:ডা\.?|অধ্যাপক|সহকারী অধ্যাপক)\s*", flags=re.IGNORECASE)


def normalize_name(name: str | None) -> str:
    """Return a comparison-friendly form of ``name``.

    Strips titles, collapses whitespace, lowercases, and removes punctuation
    that frequently varies (periods after initials, commas, hyphens). Unicode
    is preserved. Returns an empty string for ``None``.
    """

    if not name:
        return ""

    text = unicodedata.normalize("NFKC", name)
    text = normalize_whitespace(text)

    # Repeatedly strip leading titles — handles "Prof. Dr. Md. Rahman".
    for _ in range(5):
        new_text = _TITLE_PATTERN.sub("", text)
        new_text = _BANGLA_TITLE_PATTERN.sub("", new_text)
        if new_text == text:
            break
        text = new_text.strip()

    # Drop trailing punctuation like a trailing comma/period.
    text = text.strip(" ,.;:-")

    # Lowercase and collapse punctuation for the comparison form.
    text = re.sub(r"[.,;:\-_/]", " ", text)
    text = normalize_whitespace(text)
    return text.lower()


def normalize_email(email: str | None) -> str:
    """Return a lowercased, trimmed email suitable for equality comparisons.

    Does NOT validate syntax — see :mod:`app.extraction.email_extractor`.
    """

    if not email:
        return ""
    return email.strip().lower()


def normalize_url(url: str | None) -> str:
    """Strip fragments and trailing slashes from ``url`` for dedup.

    Returns an empty string for falsy input. Lowercases the scheme/host
    components so case-only differences don't multiply fetches.
    """

    if not url:
        return ""
    parts = urlparse(url)
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    netloc = parts.netloc.lower()
    return parts._replace(fragment="", path=path, netloc=netloc).geturl()


def split_tokens(name: str) -> set[str]:
    """Return the set of normalized tokens used for fuzzy name matching."""

    return {tok for tok in re.split(r"\s+", normalize_name(name)) if tok}


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Jaccard similarity between two token sets."""

    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


__all__ = [
    "normalize_whitespace",
    "normalize_name",
    "normalize_email",
    "normalize_url",
    "split_tokens",
    "jaccard",
]