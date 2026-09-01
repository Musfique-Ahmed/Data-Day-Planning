"""LLM provider Protocol + shared exceptions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMUnavailable(Exception):
    """Raised when the configured LLM provider cannot satisfy a request."""


class LLMOutputError(Exception):
    """Raised when the LLM returns malformed or hallucinated output."""


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol every concrete provider must implement."""

    model: str

    async def health_check(self) -> bool:
        """Return True iff the provider is reachable AND the model exists."""

        ...

    async def extract_faculty(self, text: str, *, schema: dict) -> dict:
        """Return a dict matching ``schema`` (Faculty fields)."""

        ...


__all__ = ["LLMProvider", "LLMUnavailable", "LLMOutputError"]