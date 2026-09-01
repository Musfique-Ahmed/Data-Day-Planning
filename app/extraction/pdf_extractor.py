"""PDF text extraction.

Uses :mod:`pdfplumber` when available; degrades gracefully to ``None`` if
the dependency is not installed so callers can compose without branching.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional, Union

BytesOrPath = Union[bytes, str, Path]


def extract_pdf_text(source: BytesOrPath) -> Optional[str]:
    """Return the concatenated text of ``source`` or ``None`` on failure.

    Accepts a path (``str`` / :class:`Path`) or raw bytes. Returns ``None``
    when ``pdfplumber`` is not installed or the document yields no text.
    """

    try:
        import pdfplumber
    except ImportError:
        return None

    if isinstance(source, (str, Path)):
        opener = pdfplumber.open(str(source))
    else:
        opener = pdfplumber.open(BytesIO(source))

    try:
        pages = [(page.extract_text() or "") for page in opener.pages]
    finally:
        opener.close()

    text = "\n\n".join(pages).strip()
    return text or None


__all__ = ["extract_pdf_text", "BytesOrPath"]