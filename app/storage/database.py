"""Async SQLite connection factory.

The repository implementations open connections via :func:`connect`. We
enable WAL mode and foreign keys once per connection. The :class:`Database`
class is a thin wrapper carrying the path so tests can swap it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from app.config import DATA_DIR, get_settings


def _resolve_path(database_url: str) -> Path:
    """Convert a ``sqlite:///<path>`` URL into a filesystem path."""

    if database_url.startswith("sqlite:///"):
        p = Path(database_url[len("sqlite:///") :])
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        return p
    if database_url.startswith("sqlite://"):
        p = Path(database_url[len("sqlite://") :])
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        return p
    return Path(database_url)


def get_database_path() -> Path:
    """Return the resolved path for the active database."""

    settings = get_settings()
    path = _resolve_path(settings.database_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@asynccontextmanager
async def connect(path: Path | None = None) -> AsyncIterator[aiosqlite.Connection]:
    """Yield an :class:`aiosqlite.Connection` with WAL + foreign keys enabled."""

    if path is None:
        path = get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(str(path))
    try:
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA foreign_keys=ON;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        await conn.commit()
        yield conn
    finally:
        await conn.close()


__all__ = ["connect", "get_database_path", "DATA_DIR"]
