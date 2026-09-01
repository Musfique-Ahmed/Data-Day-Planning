"""Faculty extraction strategies.

Implements spec §12 — three strategies invoked in order:

1. **Card** — repeating blocks like ``.faculty-card``, ``.teacher``,
   ``.staff-member``, ``.faculty-member``.
2. **Table** — ``<table>`` rows whose header contains Name/Designation/
   Department/Email.
3. **Profile** — single-faculty profile pages.

Each strategy returns a list of :class:`ExtractionResult`. The agent
combines the results, deduplicates by ``(name, institution)``, and decides
whether to escalate to the LLM based on the average confidence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from app.extraction.email_extractor import EmailExtractor, EmailHit
from app.extraction.html_parser import safe_soup, text as text_of
from app.models.faculty import EmailType, Faculty, FacultyDraft
from app.utils.normalization import normalize_name

_log = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """A draft faculty record produced by deterministic extraction."""

    draft: FacultyDraft
    confidence: float
    emails: list[EmailHit] = field(default_factory=list)
    profile_url: str | None = None
    strategy: str = "unknown"


# CSS selectors that commonly wrap a single faculty entry.
_CARD_SELECTORS: tuple[str, ...] = (
    ".faculty-card",
    ".faculty-member",
    ".faculty_member",
    ".staff-member",
    ".staff_member",
    ".teacher",
    ".teacher-card",
    ".member",
    ".card",
    "article.faculty",
    "div.faculty",
    "div.doctor",
    "div.team-member",
)


# Words that commonly label the "name" field inside a card.
_NAME_KEYWORDS: tuple[str, ...] = (
    "name",
    "faculty name",
    "doctor name",
    "full name",
    "name:",
)


# Words that commonly label the "designation" field.
_DESIGNATION_KEYWORDS: tuple[str, ...] = (
    "designation",
    "position",
    "title",
    "rank",
)

# Words that commonly label the "department" field.
_DEPARTMENT_KEYWORDS: tuple[str, ...] = (
    "department",
    "dept",
    "dept.",
    "unit",
    "subject",
)

# Words that commonly label the "email" field.
_EMAIL_KEYWORDS: tuple[str, ...] = ("email", "e-mail", "mail", "contact email")

# Words that commonly label the "research interest" field.
_RESEARCH_KEYWORDS: tuple[str, ...] = (
    "research interest",
    "research interests",
    "research area",
    "research areas",
    "research focus",
    "specialization",
    "expertise",
)


class FacultyExtractor:
    """Deterministic extraction orchestrator."""

    def __init__(self) -> None:
        self._email = EmailExtractor()

    def extract(
        self, html: str, *, institution: str, source_url: str
    ) -> list[ExtractionResult]:
        """Run all strategies and return combined results."""

        results: list[ExtractionResult] = []
        results.extend(self._from_cards(html, institution=institution, source_url=source_url))
        results.extend(self._from_tables(html, institution=institution, source_url=source_url))
        results.extend(self._from_profile(html, institution=institution, source_url=source_url))

        # Deduplicate within the page by normalized name.
        seen: set[str] = set()
        deduped: list[ExtractionResult] = []
        for r in results:
            key = (normalize_name(r.draft.name), institution.lower())
            if not r.draft.name:
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        return deduped

    def to_faculty(
        self,
        result: ExtractionResult,
        *,
        institution: str,
        source_url: str,
        institution_id: int | None = None,
        page_id: int | None = None,
    ) -> Faculty | None:
        """Convert an :class:`ExtractionResult` into a :class:`Faculty`."""

        draft = result.draft
        if not draft.name:
            return None

        email_hit = result.emails[0] if result.emails else None
        email_raw = email_hit.raw if email_hit else None
        email_normalized = email_hit.normalized if email_hit else None
        email_value = email_normalized  # Pydantic EmailStr will validate.

        email_type = EmailType.UNKNOWN
        if email_value:
            email_type = (
                EmailType.PERSONAL
                if EmailExtractor.is_generic(email_value)
                else EmailType.INSTITUTIONAL
            )

        return Faculty(
            institution_id=institution_id,
            name=draft.name.strip(),
            designation=(draft.designation or "").strip() or None,
            department=(draft.department or "").strip() or None,
            institution=institution,
            email=email_value,  # type: ignore[arg-type]
            email_raw=email_raw,
            email_normalized=email_normalized,
            email_type=email_type,
            research_interest=[s.strip() for s in (draft.research_interest or []) if s.strip()],
            profile_url=result.profile_url,  # type: ignore[arg-type]
            source_url=source_url,  # type: ignore[arg-type]
            confidence=result.confidence,
        )

    # --- strategies ----------------------------------------------------------

    def _from_cards(
        self, *, html: str, institution: str, source_url: str
    ) -> list[ExtractionResult]:
        soup = safe_soup(html)
        results: list[ExtractionResult] = []
        for selector in _CARD_SELECTORS:
            cards = soup.select(selector)
            if len(cards) < 2:
                continue  # Strategy needs *multiple* cards to be confident.
            for card in cards:
                draft = self._parse_card(card)
                if not draft.name:
                    continue
                emails = self._email.extract_from_html(str(card))
                profile_url = self._first_link(card, source_url)
                results.append(
                    ExtractionResult(
                        draft=draft,
                        confidence=self._confidence_for(draft, emails),
                        emails=emails,
                        profile_url=profile_url,
                        strategy=f"card:{selector}",
                    )
                )
            if results:
                return results
        return results

    def _from_tables(
        self, *, html: str, institution: str, source_url: str
    ) -> list[ExtractionResult]:
        soup = safe_soup(html)
        results: list[ExtractionResult] = []
        for table in soup.find_all("table"):
            header_cells = self._header_cells(table)
            if not header_cells:
                continue
            mapping = self._map_header_to_fields(header_cells)
            if "name" not in mapping:
                continue
            rows = self._data_rows(table)
            if not rows:
                continue
            for row in rows:
                draft = self._parse_row(row, mapping)
                if not draft.name:
                    continue
                emails = self._email.extract_from_html(str(row))
                results.append(
                    ExtractionResult(
                        draft=draft,
                        confidence=self._confidence_for(draft, emails),
                        emails=emails,
                        profile_url=self._first_link(row, source_url),
                        strategy="table",
                    )
                )
            if results:
                return results
        return results

    def _from_profile(
        self, *, html: str, institution: str, source_url: str
    ) -> list[ExtractionResult]:
        """Single profile page extraction — used when neither cards nor tables match."""

        soup = safe_soup(html)
        name = self._find_labeled_value(soup, _NAME_KEYWORDS)
        if not name:
            h1 = soup.find("h1")
            h2 = soup.find("h2")
            name = text_of(h1) or text_of(h2)
        if not name:
            return []

        designation = self._find_labeled_value(soup, _DESIGNATION_KEYWORDS)
        department = self._find_labeled_value(soup, _DEPARTMENT_KEYWORDS)
        research = self._find_labeled_value(soup, _RESEARCH_KEYWORDS)

        emails = self._email.extract_from_html(html)

        draft = FacultyDraft(
            name=name,
            designation=designation,
            department=department,
            institution=institution,
            email=emails[0].normalized if emails else None,
            research_interest=[research] if research else [],
        )
        return [
            ExtractionResult(
                draft=draft,
                confidence=self._confidence_for(draft, emails),
                emails=emails,
                profile_url=source_url,
                strategy="profile",
            )
        ]

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _parse_card(card) -> FacultyDraft:
        name = FacultyExtractor._find_labeled_value(card, _NAME_KEYWORDS)
        if not name:
            heading = card.find(["h1", "h2", "h3", "h4", "strong", "b"])
            if heading:
                name = text_of(heading)
        if not name:
            # Fallback: first non-empty text block in the card.
            name = text_of(card).split("\n", 1)[0].strip() if text_of(card) else ""
        designation = FacultyExtractor._find_labeled_value(card, _DESIGNATION_KEYWORDS)
        department = FacultyExtractor._find_labeled_value(card, _DEPARTMENT_KEYWORDS)
        research = FacultyExtractor._find_labeled_value(card, _RESEARCH_KEYWORDS)
        return FacultyDraft(
            name=name.strip() if name else "",
            designation=designation,
            department=department,
            research_interest=[research] if research else [],
        )

    @staticmethod
    def _parse_row(row, mapping: dict[str, int]) -> FacultyDraft:
        cells = row.find_all(["td", "th"])
        if not cells:
            return FacultyDraft(name="")
        name = FacultyExtractor._cell_by_key(mapping, cells, "name")
        designation = FacultyExtractor._cell_by_key(mapping, cells, "designation")
        department = FacultyExtractor._cell_by_key(mapping, cells, "department")
        research = FacultyExtractor._cell_by_key(mapping, cells, "research")
        return FacultyDraft(
            name=name,
            designation=designation,
            department=department,
            research_interest=[research] if research else [],
        )

    @staticmethod
    def _cell_by_key(mapping: dict[str, int], cells, key: str) -> str:
        idx = mapping.get(key)
        if idx is None or idx >= len(cells):
            return ""
        return text_of(cells[idx]).strip()

    @staticmethod
    def _header_cells(table) -> list[str]:
        header_row = None
        thead = table.find("thead")
        if thead:
            header_row = thead.find("tr")
        if header_row is None:
            # First row with at least 2 cells.
            for tr in table.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                if len(cells) >= 2:
                    header_row = tr
                    break
        if header_row is None:
            return []
        return [text_of(c).strip().lower() for c in header_row.find_all(["th", "td"])]

    @staticmethod
    def _map_header_to_fields(headers: list[str]) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for i, h in enumerate(headers):
            hl = h.lower()
            if any(k in hl for k in ("name",)):
                mapping.setdefault("name", i)
            if any(k in hl for k in ("designation", "position", "title", "rank")):
                mapping.setdefault("designation", i)
            if any(k in hl for k in ("department", "dept", "subject", "unit")):
                mapping.setdefault("department", i)
            if any(k in hl for k in ("email", "e-mail", "mail")):
                mapping.setdefault("email", i)
            if any(k in hl for k in ("research", "interest", "specialization", "expertise")):
                mapping.setdefault("research", i)
        return mapping

    @staticmethod
    def _data_rows(table) -> Iterable:
        rows = table.find_all("tr")
        # Skip the header row.
        for tr in rows[1:]:
            cells = tr.find_all(["td"])
            if len(cells) >= 2:
                yield tr

    @staticmethod
    def _find_labeled_value(scope, keywords: tuple[str, ...]) -> str | None:
        """Find text associated with a labeled span/strong/em/etc."""

        if scope is None:
            return None
        # Try <dt>...<dd> pairs.
        dts = scope.find_all("dt")
        for dt in dts:
            label = text_of(dt).strip().lower()
            if any(k in label for k in keywords):
                dd = dt.find_next("dd")
                if dd:
                    val = text_of(dd).strip()
                    if val:
                        return val

        # Try label-then-value patterns in the same paragraph.
        for el in scope.find_all(["strong", "b", "span", "em", "label"]):
            label = text_of(el).strip().lower()
            if not label:
                continue
            if any(k in label for k in keywords):
                # The value is usually a sibling text node.
                parent = el.parent
                if parent is not None:
                    full = text_of(parent).strip()
                    label_text = text_of(el).strip()
                    if full and full != label_text:
                        value = full.replace(label_text, "", 1).strip(" :;-—")
                        if value:
                            return value

        # Last resort: look for "Label: value" in any plain text.
        plain = scope.get_text("\n", strip=True) if hasattr(scope, "get_text") else ""
        for line in plain.splitlines():
            line_l = line.strip().lower()
            for kw in keywords:
                if line_l.startswith(kw):
                    after = line[len(kw):].strip(" :;-—")
                    if after:
                        return after
        return None

    @staticmethod
    def _confidence_for(draft: FacultyDraft, emails: list[EmailHit]) -> float:
        score = 0.4 if draft.name else 0.0
        if draft.designation:
            score += 0.15
        if draft.department:
            score += 0.15
        if draft.research_interest:
            score += 0.1
        if emails:
            score += 0.2
        return min(1.0, score)

    @staticmethod
    def _first_link(scope, source_url: str) -> str | None:
        if scope is None:
            return None
        a = scope.find("a[href]")
        if a is None:
            return None
        href = a.get("href")
        if not href:
            return None
        from urllib.parse import urljoin

        return urljoin(source_url, href)


__all__ = ["FacultyExtractor", "ExtractionResult"]
