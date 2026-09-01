"""Tests for app.storage.migrations.ensure_schema."""

from __future__ import annotations

import aiosqlite
import pytest

from app.storage.migrations import ensure_schema

pytestmark = pytest.mark.asyncio


async def test_ensure_schema_creates_all_tables(tmp_db: aiosqlite.Connection) -> None:
    rows = await (
        await tmp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ).fetchall()
    names = {r[0] for r in rows}
    for required in {"institutions", "pages", "faculty", "crawl_results", "runs"}:
        assert required in names


async def test_ensure_schema_is_idempotent(tmp_db: aiosqlite.Connection) -> None:
    await ensure_schema(tmp_db)
    await ensure_schema(tmp_db)