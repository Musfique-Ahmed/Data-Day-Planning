"""Application configuration.

Loads ``config/settings.yaml`` and overlays environment variables + ``.env``.
Every other module should import :class:`Settings` from here rather than
reading ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: <repo>/app/config.py → <repo>
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"


class CrawlerSettings(BaseModel):
    user_agent: str = "Mozilla/5.0 (compatible; MedicalFacultyAgent/0.1)"
    max_depth: int = 3
    max_pages_per_domain: int = 100
    timeout_ms: int = 30000
    delay_seconds: float = 1.5
    max_retries: int = 2
    respect_robots: bool = True
    follow_external_links: bool = False


class LLMSettings(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "qwen3:8b"
    num_gpu_layers: int = 35
    num_ctx: int = 4096
    temperature: float = 0.0
    prompt_version: str = "v1"


class DiscoverySettings(BaseModel):
    country: str = "Bangladesh"
    institution_type: str = "medical_college"
    extra_queries: list[str] = Field(default_factory=list)
    max_results_per_query: int = 20
    user_agent: str | None = None  # Falls back to crawler.user_agent


class ScoringSettings(BaseModel):
    department_weights: dict[str, float] = Field(default_factory=dict)
    research_keywords: dict[str, float] = Field(default_factory=dict)
    high_relevance_threshold: float = 60.0
    medium_relevance_threshold: float = 25.0


class Settings(BaseSettings):
    """Top-level settings object.

    Reads from environment variables prefixed with nothing — the field names
    match the keys in :file:`.env.example`. YAML files supply structural
    defaults that env vars override.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite:///data/database/faculty.db"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    crawler: CrawlerSettings = Field(default_factory=CrawlerSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    search_api_key: str = ""
    pipeline_run_id: str = ""
    pipeline_resume: bool = False


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _merge_yaml_into_settings(settings: Settings) -> Settings:
    """Overlay ``config/settings.yaml`` values onto the env-derived settings."""

    raw = _load_yaml(CONFIG_DIR / "settings.yaml")
    if not raw:
        return settings

    # LLM block
    if "llm" in raw:
        settings.llm = LLMSettings(**{**settings.llm.model_dump(), **raw["llm"]})

    # Crawler block
    if "crawler" in raw:
        settings.crawler = CrawlerSettings(
            **{**settings.crawler.model_dump(), **raw["crawler"]}
        )

    # Discovery block
    if "discovery" in raw:
        settings.discovery = DiscoverySettings(
            **{**settings.discovery.model_dump(), **raw["discovery"]}
        )

    # Scoring — defaults from scoring.yaml merged with settings.yaml
    scoring_yaml = _load_yaml(CONFIG_DIR / "scoring.yaml")
    if "scoring" in raw:
        scoring_yaml.update(raw["scoring"])
    if scoring_yaml:
        settings.scoring = ScoringSettings(
            **{
                **settings.scoring.model_dump(),
                "department_weights": scoring_yaml.get(
                    "department_weights", settings.scoring.department_weights
                ),
                "research_keywords": scoring_yaml.get(
                    "research_keywords", settings.scoring.research_keywords
                ),
                "high_relevance_threshold": scoring_yaml.get(
                    "high_relevance_threshold",
                    settings.scoring.high_relevance_threshold,
                ),
                "medium_relevance_threshold": scoring_yaml.get(
                    "medium_relevance_threshold",
                    settings.scoring.medium_relevance_threshold,
                ),
            }
        )

    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""

    settings = Settings()
    return _merge_yaml_into_settings(settings)


def reset_settings_cache() -> None:
    """Used by tests to reload configuration after env changes."""

    get_settings.cache_clear()


__all__ = [
    "PROJECT_ROOT",
    "CONFIG_DIR",
    "DATA_DIR",
    "Settings",
    "CrawlerSettings",
    "LLMSettings",
    "DiscoverySettings",
    "ScoringSettings",
    "get_settings",
    "reset_settings_cache",
]
