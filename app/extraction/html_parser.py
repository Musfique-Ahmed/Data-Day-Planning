"""HTML parsing helpers.

Wraps BeautifulSoup with safe defaults so callers don't have to repeat
``BeautifulSoup(html, "lxml")`` everywhere.
"""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag


def safe_soup(html: str, *, parser: str = "lxml") -> BeautifulSoup:
    """Return a BeautifulSoup with our default parser."""

    return BeautifulSoup(html or "", parser)


def text(node: Optional[Tag]) -> str:
    """Return cleaned inner text from a tag (or empty string)."""

    if node is None:
        return ""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            parts.append(text(child))
    return " ".join(s.strip() for s in parts if s and s.strip())


def visible_text(html: str) -> str:
    """Return text content with scripts/styles stripped."""

    soup = safe_soup(html)
    for tag in soup(["script", "style", "noscript", "template", "iframe"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


__all__ = ["safe_soup", "text", "visible_text"]