"""Smoke tests for the typer CLI."""

from __future__ import annotations

from typer.testing import CliRunner

from app.__main__ import cli


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "crawl" in result.output


def test_crawl_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["crawl", "--help"])
    assert result.exit_code == 0
    assert "--institution" in result.output