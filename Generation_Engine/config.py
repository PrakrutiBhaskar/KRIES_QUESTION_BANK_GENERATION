"""
Runtime configuration for the generation engine.

Values are read from environment variables (see .env.example). Nothing here
is hard-coded so the Backend module can override settings per-environment
without touching code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


@dataclass(frozen=True)
class Settings:
    # Groq API
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_timeout_seconds: float = _env_float("GROQ_TIMEOUT_SECONDS", 30.0)
    groq_temperature: float = _env_float("GROQ_TEMPERATURE", 0.7)

    # Generation / validation behaviour
    max_regeneration_retries: int = _env_int("MAX_REGENERATION_RETRIES", 2)
    near_duplicate_similarity_threshold: float = _env_float(
        "NEAR_DUPLICATE_SIMILARITY_THRESHOLD", 0.90
    )
    max_batch_count: int = _env_int("MAX_BATCH_COUNT", 25)


settings = Settings()
