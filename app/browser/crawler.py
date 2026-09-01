"""Controlled BFS crawler built on Playwright.

Implements spec §11 — async, throttled, with retry/backoff and per-domain
quotas. Yields :class:`CrawlYield` envelopes so the orchestration layer
can consume both the canonical :class:`CrawlResult` and the transient
``links`` / ``anchors`` data without smuggling state onto the model.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic
from typing import AsyncIterator
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page, TimeoutError as PWTimeout

from app.browser.browser import BrowserManager
from app.browser.link_ranker import LinkRanker
from app.browser.robots import RobotsCache
from app.models.crawl_result import CrawlResult, CrawlStatus, CrawlYield
from app.utils.hashing import content_hash
from app.utils.normalization import normalize_url

_log = logging.getLogger(__name__)


@dataclass
class CrawlLimits:
    """Tunable limits applied per crawl run."""

    max_depth: int = 3
    max_pages_per_domain: int = 100
    timeout_ms: int = 30000
    delay_seconds: float = 1.5
    max_retries: int = 2
    follow_external_links: bool = False
    min_link_score: float = 0.0  # BFS threshold for queued links


class Crawler:
    """A throttled BFS crawler."""

    def __init__(
        self,
        manager: BrowserManager,
        *,
        limits: CrawlLimits | None = None,
        user_agent: str | None = None,
        respect_robots: bool = True,
    ) -> None:
        self._manager = manager
        self._limits = limits or CrawlLimits()
        self._user_agent = user_agent or manager._user_agent
        self._robots = RobotsCache(self._user_agent) if respect_robots else None
        self._link_ranker = LinkRanker()

    @property
    def limits(self) -> CrawlLimits:
        return self._limits

    @property
    def link_ranker(self) -> LinkRanker:
        return self._link_ranker

    async def crawl(self, start_url: str) -> AsyncIterator[CrawlYield]:
        """Crawl starting from ``start_url`` and yield :class:`CrawlYield`s."""

        visited: set[str] = set()
        per_domain_count: dict[str, int] = defaultdict(int)
        # BFS queue: (normalized_url, depth)
        queue: deque[tuple[str, int]] = deque([(normalize_url(start_url), 0)])
        start_domain = urlparse(start_url).netloc.lower()

        # Reuse one context per crawl to keep cookies isolated.
        ctx: BrowserContext = await self._manager.new_context()

        try:
            while queue:
                url, depth = queue.popleft()
                if depth > self._limits.max_depth:
                    continue
                if not url or url in visited:
                    continue
                visited.add(url)

                domain = urlparse(url).netloc.lower()
                if (
                    not self._limits.follow_external_links
                    and domain != start_domain
                ):
                    continue
                if per_domain_count[domain] >= self._limits.max_pages_per_domain:
                    continue

                if self._robots is not None and not await self._robots.can_fetch(url):
                    yield CrawlYield(
                        result=CrawlResult(
                            url=url,
                            status=CrawlStatus.SKIPPED,
                            depth=depth,
                            error="robots.txt disallows",
                        ),
                    )
                    continue

                # Honour the per-request delay.
                await asyncio.sleep(self._limits.delay_seconds)

                result, links, anchors = await self._fetch_one(ctx, url, depth)

                if result.status == CrawlStatus.OK:
                    per_domain_count[domain] += 1

                # Score and sort discovered links descending; skip below threshold.
                scored = sorted(
                    (
                        (
                            normalize_url(link),
                            self._link_ranker.score(link, anchors.get(link, "")),
                        )
                        for link in links
                    ),
                    key=lambda kv: kv[1],
                    reverse=True,
                )
                for norm_link, score in scored:
                    if score < self._limits.min_link_score:
                        continue
                    if not norm_link:
                        continue
                    queue.append((norm_link, depth + 1))

                yield CrawlYield(result=result, links=tuple(links), anchors=anchors)
        finally:
            await ctx.close()

    async def _fetch_one(
        self, ctx: BrowserContext, url: str, depth: int
    ) -> tuple[CrawlResult, list[str], dict[str, str]]:
        """Fetch one URL with retry/backoff and capture result + sidecar data.

        Returns ``(CrawlResult, links, anchors)`` so the caller can persist
        the canonical record and queue discovered links separately.
        """

        last_exc: Exception | None = None
        start = monotonic()

        for attempt in range(self._limits.max_retries + 1):
            page: Page | None = None
            try:
                page = await ctx.new_page()
                page.set_default_navigation_timeout(self._limits.timeout_ms)
                page.set_default_timeout(self._limits.timeout_ms)
                response = await page.goto(url, wait_until="domcontentloaded")
                http_status = response.status if response else None
                html = await page.content()
                anchors: list[tuple[str, str]] = []
                try:
                    handle = await page.query_selector_all("a[href]")
                    for el in handle:
                        href = await el.get_attribute("href")
                        text = (await el.inner_text()) if href else ""
                        if href:
                            anchors.append((href, text.strip()))
                except Exception as exc:  # pragma: no cover - best-effort
                    _log.debug("link extraction failed on %s: %s", url, exc)
                finally:
                    await page.close()

                final_url = page.url if page else url
                links = [urljoin(url, h) for h, _ in anchors]
                anchor_lookup = {urljoin(url, h): a for h, a in anchors}

                duration_ms = int((monotonic() - start) * 1000)
                if http_status and http_status >= 400:
                    status = (
                        CrawlStatus.HTTP_ERROR
                        if http_status < 500
                        else CrawlStatus.NETWORK_ERROR
                    )
                    return (
                        CrawlResult(
                            url=url,
                            final_url=final_url,
                            status=status,
                            http_status=http_status,
                            duration_ms=duration_ms,
                            depth=depth,
                            error=f"HTTP {http_status}",
                        ),
                        [],
                        {},
                    )

                return (
                    CrawlResult(
                        url=url,
                        final_url=final_url,
                        status=CrawlStatus.OK,
                        http_status=http_status,
                        duration_ms=duration_ms,
                        depth=depth,
                        page_type="page",
                        content_hash=content_hash(html),
                        bytes_downloaded=len(html.encode("utf-8")),
                    ),
                    links,
                    anchor_lookup,
                )

            except PWTimeout as exc:
                last_exc = exc
                if attempt >= self._limits.max_retries:
                    return (
                        CrawlResult(
                            url=url,
                            status=CrawlStatus.TIMEOUT,
                            depth=depth,
                            duration_ms=int((monotonic() - start) * 1000),
                            error=str(exc),
                    ),
                        [],
                        {},
                    )
                await asyncio.sleep(self._limits.delay_seconds * (attempt + 1))

            except Exception as exc:  # pragma: no cover - defensive
                last_exc = exc
                if page is not None:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if attempt >= self._limits.max_retries:
                    return (
                        CrawlResult(
                            url=url,
                            status=CrawlStatus.NETWORK_ERROR,
                            depth=depth,
                            duration_ms=int((monotonic() - start) * 1000),
                            error=str(exc),
                        ),
                        [],
                        {},
                    )
                await asyncio.sleep(self._limits.delay_seconds * (attempt + 1))

        # Should never get here.
        return (
            CrawlResult(
                url=url,
                depth=depth,
                status=CrawlStatus.NETWORK_ERROR,
                error=str(last_exc) if last_exc else "unknown",
            ),
            [],
            {},
        )


__all__ = ["Crawler", "CrawlLimits"]