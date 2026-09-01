"""Hashing helpers used for cache keys and content deduplication."""

from __future__ import annotations

import hashlib


def content_hash(content: str | bytes) -> str:
    """Return a SHA-256 hex digest of the given content."""

    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def normalize_for_cache_key(*parts: str | int | float | None) -> str:
    """Build a deterministic cache key from arbitrary string parts.

    Used to compose keys like ``"<hash>|v1|qwen3:8b"``.
    """

    safe = [str(p) if p is not None else "" for p in parts]
    return "|".join(safe)


__all__ = ["content_hash", "normalize_for_cache_key"]