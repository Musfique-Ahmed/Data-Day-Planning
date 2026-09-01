"""Tests for app.agents.crawler_agent.classify_page."""

from __future__ import annotations

from app.agents.crawler_agent import classify_page
from app.models.page import PageType


def test_faculty_directory_tokens() -> None:
    for token in ("faculty-member", "faculty_members", "faculty_member"):
        assert classify_page(f"https://x.com/{token}") == PageType.FACULTY_DIRECTORY


def test_teacher_anchor_classifies_staff_list() -> None:
    assert classify_page("https://x.com/people", {"a": "Our Teachers"}) == PageType.STAFF_LIST


def test_department_classifies_department() -> None:
    assert classify_page("https://x.com/dept") == PageType.DEPARTMENT


def test_unrelated_url_returns_other() -> None:
    assert classify_page("https://x.com/contact") == PageType.OTHER