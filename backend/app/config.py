"""All settings come from environment variables, every one has a safe default.

The app must start with zero configuration (no .env, no API key). Without an
ANTHROPIC_API_KEY it runs in "offline" mode: deterministic parts work fully,
LLM parts fall back to cached outputs for the bundled sample files.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_samples_dir() -> str:
    here = Path(__file__).resolve()
    for candidate in (here.parents[1] / "data" / "samples", here.parents[2] / "data" / "samples"):
        if candidate.is_dir():
            return str(candidate)
    return str(here.parents[1] / "data" / "samples")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+psycopg://bidbench:bidbench@localhost:5432/bidbench"
    anthropic_api_key: str = ""
    llm_model_smart: str = "claude-sonnet-5-5"
    llm_model_fast: str = "claude-haiku-5-5"
    seed_samples: bool = True
    samples_dir: str = _default_samples_dir()
    cache_dir: str = str(Path(_default_samples_dir()).parent / "cache")  # LLM outputs keyed by file hash
    work_dir: str = "/tmp/bidbench"
    sim_seed: int = 42
    worker_poll_seconds: float = 1.0
    max_upload_mb: int = 50
    log_level: str = "info"

    @property
    def llm_mode(self) -> str:
        return "live" if self.anthropic_api_key.strip() else "offline"


@lru_cache
def get_settings() -> Settings:
    return Settings()
