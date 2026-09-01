"""Command-line entry point for the Data Day Planning pipeline.

Wires configuration → logging → database schema → browser → crawler → storage.
Use ``python -m app crawl --institution NAME`` to crawl a single institution.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

import typer

from app.agents.crawler_agent import CrawlerAgent
from app.browser.browser import BrowserManager
from app.config import get_settings
from app.storage.database import connect
from app.storage.migrations import ensure_schema
from app.storage.sqlite_repository import SQLiteInstitutionRepository
from app.utils.logging import configure_logging

cli = typer.Typer(help="Data Day Planning — faculty crawl CLI")


@cli.command()
def crawl(
    institution: str = typer.Option(
        ...,
        "--institution",
        "-i",
        help="Institution name (must exist in the database).",
    ),
    limit: int = typer.Option(
        20, "--limit", "-n", help="Soft cap on pages per crawl (informational)."
    ),
) -> None:
    """Crawl one institution's website end-to-end."""

    run_id = uuid.uuid4().hex[:12]
    configure_logging("INFO", run_id=run_id)
    asyncio.run(_crawl(institution=institution, run_id=run_id, limit=limit))


async def _crawl(*, institution: str, run_id: str, limit: int) -> None:
    del limit, run_id  # reserved for future use (rate-limit, telemetry)
    settings = get_settings()

    async with connect() as conn:
        await ensure_schema(conn)
        inst_repo = SQLiteInstitutionRepository()
        rows = await inst_repo.list_all(conn)
        target = next(
            (r for r in rows if r.name.lower() == institution.lower()), None
        )
        if target is None or target.id is None:
            typer.echo(f"Institution not found: {institution}", err=True)
            raise typer.Exit(code=2)

        mgr = BrowserManager(user_agent=settings.crawler.user_agent)
        await mgr.start()
        try:
            agent = CrawlerAgent()
            async for page in agent.crawl_institution(
                institution_id=target.id,
                start_url=str(target.website),
                manager=mgr,
                conn=conn,
            ):
                typer.echo(
                    f"crawled: {page.url} "
                    f"type={page.page_type.value} "
                    f"status={page.crawl_status.value} "
                    f"depth={page.depth}"
                )
        finally:
            await mgr.stop()


@cli.command()
def verify(
    institution: Optional[str] = typer.Option(
        None,
        "--institution",
        "-i",
        help="Verify only the named institution (defaults to all).",
    ),
) -> None:
    """Mark institutions as verified in the database."""

    configure_logging("INFO", run_id=uuid.uuid4().hex[:12])
    asyncio.run(_verify(institution=institution))


async def _verify(*, institution: Optional[str]) -> None:
    async with connect() as conn:
        await ensure_schema(conn)
        repo = SQLiteInstitutionRepository()
        if institution is None:
            rows = await repo.list_all(conn)
            for row in rows:
                if row.id is not None:
                    await repo.verify(conn, row.id)
                    typer.echo(f"verified: {row.name}")
        else:
            rows = await repo.list_all(conn)
            target = next(
                (r for r in rows if r.name.lower() == institution.lower()),
                None,
            )
            if target is None or target.id is None:
                typer.echo(f"Institution not found: {institution}", err=True)
                raise typer.Exit(code=2)
            await repo.verify(conn, target.id)
            typer.echo(f"verified: {target.name}")


if __name__ == "__main__":
    cli()


__all__ = ["cli"]