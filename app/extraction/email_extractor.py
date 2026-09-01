"""Deterministic email extraction.

We extract emails from three sources, in this order of authority:

1. ``mailto:`` link ``href`` attributes (the strongest signal — these are
   explicitly linked).
2. Plain text inside the HTML (regex over visible text).
3. Obfuscated forms like ``name [at] domain [dot] tld`` (best-effort).

Extracted emails are returned **as found**. We never generate or infer
emails. Both ``email_raw`` and ``email_normalized`` are recorded; the raw
form is preserved for provenance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.utils.normalization import normalize_email


# Conservative RFC-5322-lite pattern. Permissive enough for the wild,
# strict enough that it doesn't accept arbitrary punctuation.
_EMAIL_RE = re.compile(
    r"""
    (?<![\w.+-])                       # left boundary
    [A-Za-z0-9._%+\-]+                 # local part
    @
    (?:[A-Za-z0-9\-]+\.)+              # domain labels
    [A-Za-z]{2,24}                     # TLD
    (?![\w.+-])                        # right boundary
    """,
    re.VERBOSE,
)

# Obfuscated forms: "name [at] domain [dot] tld", "name(at)domain(dot)tld".
_OBFUSCATED_RE = re.compile(
    r"""
    (?<![\w.+-])
    [A-Za-z0-9._%+\-]+                  # local part
    \s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\{at\}|@\s*)\s*
    (?:[A-Za-z0-9\-]+\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{dot\}|\.)\s*)+
    [A-Za-z]{2,24}
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Generic webmail providers — used downstream for email_type classification.
_GENERIC_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
    }
)


@dataclass(frozen=True)
class EmailHit:
    """A single email found in a document."""

    raw: str
    normalized: str
    source: str  # 'mailto' | 'text' | 'obfuscated'


class EmailExtractor:
    """Pull emails out of an HTML document."""

    def __init__(self, *, include_obfuscated: bool = True) -> None:
        self._include_obfuscated = include_obfuscated

    @staticmethod
    def is_generic(email: str) -> bool:
        """True for webmail addresses (gmail/yahoo/...)."""

        if "@" not in email:
            return False
        domain = email.rsplit("@", 1)[-1].lower()
        return domain in _GENERIC_DOMAINS

    def extract_from_html(self, html: str) -> list[EmailHit]:
        """Return all unique emails found in ``html``."""

        from app.extraction.html_parser import safe_soup

        hits: dict[str, EmailHit] = {}

        soup = safe_soup(html)

        # 1. mailto: links.
        for a in soup.select("a[href]"):
            href = a.get("href", "") or ""
            if not isinstance(href, str):
                continue
            if href.lower().startswith("mailto:"):
                addr = href[len("mailto:") :].split("?", 1)[0]
                addr = addr.strip()
                if _EMAIL_RE.fullmatch(addr):
                    self._add(hits, addr, "mailto")

        # 2. Visible text.
        from app.extraction.html_parser import visible_text

        visible = visible_text(html)
        for m in _EMAIL_RE.finditer(visible):
            self._add(hits, m.group(0), "text")

        # 3. Obfuscated forms.
        if self._include_obfuscated:
            for m in _OBFUSCATED_RE.finditer(html):
                decoded = self._decode_obfuscated(m.group(0))
                if decoded and _EMAIL_RE.fullmatch(decoded):
                    self._add(hits, decoded, "obfuscated")

        return list(hits.values())

    @staticmethod
    def _decode_obfuscated(text: str) -> str | None:
        """Replace obfuscation tokens ([at], (at), {at}, ' at ') with @ / ."""

        def _sub(m: re.Match[str]) -> str:
            return "@" if m.group(1).lower() == "at" else "."

        # Bracketed forms: [at], [dot], (at), (dot), {at}, {dot}.
        bracket_patterns: tuple[str, ...] = (
            r"\s*\[\s*(at|dot)\s*\]\s*",
            r"\s*\(\s*(at|dot)\s*\)\s*",
            r"\{(at|dot)\}",
        )
        for pattern in bracket_patterns:
            text = re.sub(pattern, _sub, text, flags=re.IGNORECASE)

        # Common "name at domain dot tld" pattern.
        text = re.sub(r"\s+at\s+", "@", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+dot\s+", ".", text, flags=re.IGNORECASE)
        return text.strip() or None

    @staticmethod
    def _add(hits: dict[str, EmailHit], raw: str, source: str) -> None:
        norm = normalize_email(raw)
        if not norm:
            return
        if norm not in hits:
            hits[norm] = EmailHit(raw=raw, normalized=norm, source=source)


__all__ = ["EmailExtractor", "EmailHit"]