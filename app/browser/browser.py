"""Playwright browser lifecycle.

We launch a single Chromium instance per :func:`browser_session` async
context manager. The session is shared across many crawls; we open fresh
contexts per domain to isolate cookies / storage.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.config import get_settings

_log = logging.getLogger(__name__)


class BrowserManager:
    """Owns the long-lived ``Browser`` instance."""

    def __init__(self, user_agent: str | None = None) -> None:
        self._user_agent = user_agent or get_settings().crawler.user_agent
        self._playwright = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        _log.debug("Browser launched (headless=True)")

    async def new_context(self) -> BrowserContext:
        if self._browser is None:
            await self.start()
        assert self._browser is not None
        return await self._browser.new_context(
            user_agent=self._user_agent,
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


@asynccontextmanager
async def browser_session(user_agent: str | None = None) -> AsyncIterator[BrowserManager]:
    """Async context manager that yields a started :class:`BrowserManager`."""

    mgr = BrowserManager(user_agent=user_agent)
    try:
        await mgr.start()
        yield mgr
    finally:
        await mgr.stop()


async def fetch_page(
    mgr: BrowserManager,
    url: str,
    *,
    timeout_ms: int = 30000,
    wait_until: str = "domcontentloaded",
    user_data_dir: Path | None = None,
) -> tuple[BrowserContext, Page]:
    """Open a fresh context + page and navigate to ``url``.

    Caller is responsible for closing the context. Returns both so the caller
    can extract the page content, screenshot, etc.
    """

    ctx = await mgr.new_context()
    page = await ctx.new_page()
    page.set_default_navigation_timeout(timeout_ms)
    page.set_default_timeout(timeout_ms)
    await page.goto(url, wait_until=wait_until)
    return ctx, page


__all__ = ["BrowserManager", "browser_session", "fetch_page"]