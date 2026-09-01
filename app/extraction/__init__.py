"""Extraction module: HTML parsing, email extraction, faculty extraction."""

from app.extraction.email_extractor import EmailExtractor, EmailHit
from app.extraction.faculty_extractor import FacultyExtractor, ExtractionResult
from app.extraction.html_parser import safe_soup, text, visible_text

__all__ = [
    "EmailExtractor",
    "EmailHit",
    "FacultyExtractor",
    "ExtractionResult",
    "safe_soup",
    "text",
    "visible_text",
]