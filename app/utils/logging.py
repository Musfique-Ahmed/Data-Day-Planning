"""Structured run logger used by every CLI command.

A single :func:`get_logger` factory gives each subsystem its own
``rich.logging.RichHandler`` console output and writes rotating logs to
``data/logs/``. The pipeline orchestrator uses :class:`RunSummary` to
emit the spec §28 summary at the end of a run.
"""

from __future__ import annotations

import logging
import logging.handlers
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.logging import RichHandler

from app.config import DATA_DIR

LOG_DIR = DATA_DIR / "logs"

# Module-level singleton state for the run_id filter so subsequent calls
# to ``configure_logging(..., run_id=X)`` update the active value instead
# of stacking duplicate filters on every handler.
_ACTIVE_RUN_ID: dict[str, str] = {"value": "default"}
_RUN_ID_FILTER_INSTALLED: bool = False


class _RunIdFilter(logging.Filter):
    """Inject ``run_id`` onto every log record from the singleton value."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if not hasattr(record, "run_id"):
            record.run_id = _ACTIVE_RUN_ID["value"]
        return True


def configure_logging(level: str = "INFO", run_id: str = "default") -> logging.Logger:
    """Configure the root logger. Idempotent."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Update the singleton run_id before (re)installing handlers so the very
    # first record after a reconfigure picks up the new value.
    _ACTIVE_RUN_ID["value"] = run_id

    # Remove existing handlers (avoid duplicates across re-configurations).
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | run=%(run_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = RichHandler(rich_tracebacks=True, show_path=False)
    console.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "agent.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Attach the singleton filter to every handler — only once globally.
    global _RUN_ID_FILTER_INSTALLED
    if not _RUN_ID_FILTER_INSTALLED:
        run_filter = _RunIdFilter()
        for h in root.handlers:
            h.addFilter(run_filter)
        _RUN_ID_FILTER_INSTALLED = True

    return root


def get_logger(name: str) -> logging.Logger:
    """Return a child logger. Call :func:`configure_logging` once at startup."""

    return logging.getLogger(name)


@dataclass
class RunSummary:
    """Aggregated metrics for a single pipeline run."""

    run_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    institutions_discovered: int = 0
    institutions_verified: int = 0

    pages_crawled: int = 0
    pages_failed: int = 0

    faculty_extracted: int = 0
    faculty_valid: int = 0
    faculty_duplicates: int = 0

    emails_found: int = 0
    emails_institutional: int = 0
    emails_other: int = 0

    relevance_high: int = 0
    relevance_medium: int = 0
    relevance_low: int = 0

    review_pending: int = 0
    review_approved: int = 0

    output_path: str = ""

    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "institutions": {
                "discovered": self.institutions_discovered,
                "verified": self.institutions_verified,
            },
            "pages": {
                "crawled": self.pages_crawled,
                "failed": self.pages_failed,
            },
            "faculty": {
                "extracted": self.faculty_extracted,
                "valid": self.faculty_valid,
                "duplicates": self.faculty_duplicates,
            },
            "emails": {
                "found": self.emails_found,
                "institutional": self.emails_institutional,
                "other": self.emails_other,
            },
            "relevance": {
                "high": self.relevance_high,
                "medium": self.relevance_medium,
                "low": self.relevance_low,
            },
            "review": {
                "pending": self.review_pending,
                "approved": self.review_approved,
            },
            "output_path": self.output_path,
        }
        if self.extras:
            d["extras"] = self.extras
        return d

    def render_text(self) -> str:
        """Format the run summary as a human-readable console block."""

        lines = [
            "=========================================",
            "MEDICAL FACULTY AGENT",
            "=========================================",
            f"Run ID: {self.run_id}",
            "",
            "Institutions:",
            f"  Discovered:       {self.institutions_discovered}",
            f"  Verified:         {self.institutions_verified}",
            "",
            "Pages:",
            f"  Crawled:          {self.pages_crawled}",
            f"  Failed:           {self.pages_failed}",
            "",
            "Faculty:",
            f"  Extracted:        {self.faculty_extracted}",
            f"  Valid:            {self.faculty_valid}",
            f"  Duplicates:       {self.faculty_duplicates}",
            "",
            "Emails:",
            f"  Found:            {self.emails_found}",
            f"  Institutional:    {self.emails_institutional}",
            f"  Other:            {self.emails_other}",
            "",
            "Relevance:",
            f"  High:             {self.relevance_high}",
            f"  Medium:           {self.relevance_medium}",
            f"  Low:              {self.relevance_low}",
            "",
            "Review:",
            f"  Pending:          {self.review_pending}",
            f"  Approved:         {self.review_approved}",
            "",
            "Output:",
            f"  {self.output_path or '(none)'}",
            "=========================================",
        ]
        return "\n".join(lines)


__all__ = ["configure_logging", "get_logger", "RunSummary", "LOG_DIR"]


def write_summary(path: Path, summary: RunSummary) -> Path:
    """Persist the run summary as JSON next to the data exports."""

    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    return path
