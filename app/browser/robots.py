"""Minimal robots.txt fetcher + cache.

Best-effort: if fetching robots.txt fails we *proceed* (the spec says we
should respect robots where applicable but never block legitimate work).
The cache lives in-memory for the lifetime of a single pipeline run.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

_log = logging.getLogger(__name__)


class RobotsCache:
    """Per-domain robots.txt cache."""

    def __init__(self, user_agent: str, timeout: float = 10.0) -> None:
        self._ua = user_agent
        self._timeout = timeout
        self._cache: dict[str, Optional[RobotFileParser]] = {}

    def _origin(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def can_fetch(self, url: str) -> bool:
        origin = self._origin(url)
        parser = await self._get(origin)
        if parser is None:
            return True  # No robots.txt → allow.
        try:
            return parser.can_fetch(self._ua, url)
        except Exception as exc:  # pragma: no cover - defensive
            _log.debug("robots.can_fetch error for %s: %s", url, exc)
            return True

    async def _get(self, origin: str) -> Optional[RobotFileParser]:
        if origin in self._cache:
            return self._cache[origin]

        robots_url = urljoin(origin, "/robots.txt")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(robots_url, follow_redirects=True)
            if resp.status_code != 200 or not resp.text:
                self._cache[origin] = None
                return None
            parser = RobotFileParser()
            parser.parse(resp.text.splitlines())
            self._cache[origin] = parser
            return parser
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            _log.debug("robots.txt fetch failed for %s: %s", origin, exc)
            self._cache[origin] = None
            return None


__all__ = ["RobotsCache"]