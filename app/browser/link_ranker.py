"""Classify and rank candidate faculty-directory URLs.

Implements spec §10 — given an institution's homepage, surface the URLs
most likely to be faculty pages. Pure logic; no network access.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse

# URL path components that suggest faculty / staff pages.
_URL_KEYWORDS: tuple[str, ...] = (
    "faculty",
    "faculty-members",
    "faculty_member",
    "academic-staff",
    "academic_staff",
    "staff",
    "teachers",
    "professors",
    "department",
    "departments",
    "medicine",
    "public-health",
    "community-medicine",
    "medical-education",
    "our-faculty",
    "our_team",
    "people",
)

# Anchor text that suggests a faculty directory link.
_ANCHOR_KEYWORDS: tuple[str, ...] = (
    "faculty",
    "faculty members",
    "academic staff",
    "our faculty",
    "teachers",
    "departments",
    "professor",
    "staff",
    "people",
)


@dataclass(frozen=True)
class LinkSignal:
    """A URL plus a score and the signal that produced the score."""

    url: str
    anchor: str
    score: float
    matched_keyword: str | None = None


class LinkRanker:
    """Score URLs against the faculty-page keywords.

    Higher scores indicate higher likelihood of being a faculty directory.
    """

    def __init__(self, url_keywords: tuple[str, ...] = _URL_KEYWORDS) -> None:
        self._url_keywords = tuple(k.lower() for k in url_keywords)

    @staticmethod
    def _path_segments(url: str) -> list[str]:
        path = urlparse(url).path or ""
        return [unquote(seg) for seg in path.split("/") if seg]

    def score(self, url: str, anchor: str = "") -> float:
        """Return a heuristic score in ``[0, 100]``.

        The score combines URL-keyword matches and anchor-text matches.
        """

        score = 0.0
        path_segs = [s.lower() for s in self._path_segments(url)]
        path_blob = "/".join(path_segs)

        matched_url_keyword: str | None = None
        for kw in self._url_keywords:
            if kw in path_blob:
                score += 30.0
                matched_url_keyword = kw
                # Extra weight for shorter, more specific paths.
                if len(path_segs) <= 2:
                    score += 10.0
                break

        anchor_lower = anchor.lower().strip()
        for kw in _ANCHOR_KEYWORDS:
            if kw in anchor_lower:
                score += 20.0
                break

        # Penalise very long paths (likely deep, non-index pages).
        if len(path_segs) > 5:
            score -= 5.0

        # Penalise obvious non-content paths.
        bad = ("login", "wp-admin", "wp-login", "?", "#", "javascript:")
        if any(b in url.lower() for b in bad):
            score -= 50.0

        return max(0.0, min(100.0, score))

    def rank(self, candidates: list[tuple[str, str]]) -> list[LinkSignal]:
        """Score and sort ``(url, anchor)`` tuples by descending score."""

        scored: list[LinkSignal] = []
        seen: set[str] = set()
        for url, anchor in candidates:
            norm = url.split("#", 1)[0]
            if norm in seen:
                continue
            seen.add(norm)
            s = self.score(url, anchor)
            scored.append(LinkSignal(url=url, anchor=anchor, score=s))
        scored.sort(key=lambda x: (-x.score, x.url))
        return scored


__all__ = ["LinkRanker", "LinkSignal"]