"""Shared pytest fixtures."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def tmp_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield an in-memory-ish aiosqlite connection with schema applied.

    Uses a temporary file rather than ``:memory:`` so multiple connections
    can share the same database if needed.
    """

    from app.storage.migrations import ensure_schema

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as fh:
        path = Path(fh.name)
    try:
        conn = await aiosqlite.connect(str(path))
        await conn.execute("PRAGMA foreign_keys=ON;")
        await ensure_schema(conn)
        await conn.commit()
        yield conn
        await conn.close()
    finally:
        path.unlink(missing_ok=True)