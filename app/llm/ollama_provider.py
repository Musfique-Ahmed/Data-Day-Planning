"""Ollama-backed :class:`LLMProvider` implementation."""

from __future__ import annotations

import json
import logging
from typing import Any

import ollama
from pydantic import ValidationError

from app.config import LLMSettings, get_settings
from app.llm.base import LLMOutputError, LLMProvider, LLMUnavailable
from app.models.faculty import FacultyDraft

_log = logging.getLogger(__name__)

# Keys the LLM is allowed to return; everything else is dropped before
# FacultyDraft validation.
_FACULTY_KEYS: tuple[str, ...] = (
    "name",
    "designation",
    "department",
    "institution",
    "email",
    "research_interest",
)


class OllamaProvider:
    """Async LLM provider backed by a local Ollama daemon."""

    def __init__(self, settings: LLMSettings | None = None) -> None:
        s = settings or get_settings().llm
        self._settings = s
        self.model = s.model
        self._client = ollama.AsyncClient(host=s.base_url)

    async def health_check(self) -> bool:
        try:
            listing = await self._client.list()
        except (ollama.ResponseError, ConnectionError, TimeoutError) as exc:
            raise LLMUnavailable(str(exc)) from exc
        names = {m.get("name") for m in (listing or {}).get("models", [])}
        return self.model in names

    async def extract_faculty(self, text: str, *, schema: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(text, schema)
        try:
            resp = await self._client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={
                    "num_gpu_layers": self._settings.num_gpu_layers,
                    "num_ctx": self._settings.num_ctx,
                    "temperature": self._settings.temperature,
                },
            )
        except (ollama.ResponseError, ConnectionError, TimeoutError) as exc:
            raise LLMUnavailable(str(exc)) from exc

        raw = resp.get("message", {}).get("content", "")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMOutputError(f"non-JSON response: {raw[:200]!r}") from exc

        if not isinstance(parsed, dict):
            raise LLMOutputError(f"expected object, got {type(parsed).__name__}")

        draft = {k: parsed.get(k) for k in _FACULTY_KEYS}
        try:
            FacultyDraft.model_validate(draft)
        except ValidationError as exc:
            raise LLMOutputError(str(exc)) from exc
        return draft

    def _build_prompt(self, text: str, schema: dict[str, Any]) -> str:
        return (
            "Extract faculty records from this page. "
            f"Return JSON with these keys: {list(_FACULTY_KEYS)}. "
            "Do not invent fields. Leave a field null if not present.\n\n"
            f"--- PAGE ---\n{text}\n--- END ---"
        )


__all__ = ["OllamaProvider"]