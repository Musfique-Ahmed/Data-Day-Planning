"""Tests for app.utils.logging._RunIdFilter singleton behavior."""

from __future__ import annotations

import logging

from app.utils.logging import _ACTIVE_RUN_ID, configure_logging


def test_singleton_run_id_updates_on_reconfigure() -> None:
    configure_logging("INFO", run_id="run-a")
    assert _ACTIVE_RUN_ID["value"] == "run-a"
    configure_logging("INFO", run_id="run-b")
    assert _ACTIVE_RUN_ID["value"] == "run-b"


def test_log_records_carry_active_run_id() -> None:
    configure_logging("INFO", run_id="run-z")
    logger = logging.getLogger("test_logging")
    record = logger.makeRecord(
        "name", logging.INFO, "fn", 1, "msg", None, None
    )
    # The filter is attached at module import time on the root logger.
    root = logging.getLogger()
    for h in root.handlers:
        for f in h.filters:
            f.filter(record)
    assert getattr(record, "run_id", None) == "run-z"