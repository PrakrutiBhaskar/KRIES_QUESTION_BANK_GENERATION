"""
Runtime configuration for the generation engine.

Values are read from environment variables (see .env.example). Nothing here
is hard-coded so the Backend module can override settings per-environment
without touching code.

Note on `.env`: `load_dotenv()` runs at import, and every field resolves
through a `default_factory` rather than a class-level default, so values are
read when `Settings()` is constructed rather than when this module is first
imported. That ordering matters — a class-level `os.getenv(...)` default
freezes whatever the environment looked like at import time, which means a
`.env` file loaded later is silently ignored.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # python-dotenv is optional at runtime, required for local dev
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env_str(name: str, default: str):
    return lambda: os.getenv(name, default)


def _env_int(name: str, default: int):
    def resolve() -> int:
        val = os.getenv(name)
        return int(val) if val else default

    return resolve


def _env_float(name: str, default: float):
    def resolve() -> float:
        val = os.getenv(name)
        return float(val) if val else default

    return resolve


def _env_bool(name: str, default: bool):
    def resolve() -> bool:
        val = os.getenv(name)
        if not val:
            return default
        return val.strip().lower() in {"1", "true", "yes", "on"}

    return resolve


@dataclass(frozen=True)
class Settings:
    # --- Groq API ---
    groq_api_key: str = field(default_factory=_env_str("GROQ_API_KEY", ""))
    groq_base_url: str = field(
        default_factory=_env_str("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    )
    groq_model: str = field(
        # llama-3.3-70b-versatile was deprecated by Groq (announced 2026-06-17,
        # decommissioned 2026-08-16). Groq's recommended replacement for this
        # use case is openai/gpt-oss-120b; verify against
        # https://console.groq.com/docs/deprecations if this default ever
        # starts failing with model_decommissioned.
        default_factory=_env_str("GROQ_MODEL", "openai/gpt-oss-120b")
    )
    groq_timeout_seconds: float = field(
        default_factory=_env_float("GROQ_TIMEOUT_SECONDS", 30.0)
    )
    groq_temperature: float = field(default_factory=_env_float("GROQ_TEMPERATURE", 0.7))

    # Transport-level retries (429s / transient 5xx). Distinct from the
    # generation-level regeneration retries below.
    groq_max_retries: int = field(default_factory=_env_int("GROQ_MAX_RETRIES", 3))
    groq_retry_backoff_seconds: float = field(
        default_factory=_env_float("GROQ_RETRY_BACKOFF_SECONDS", 1.0)
    )

    # Client-side approximation of Groq's tokens-per-minute (TPM) limit.
    # The client proactively waits before a call likely to blow this budget
    # instead of firing it and eating a 429 + backoff. 8000 matches the
    # `on_demand` free tier seen in practice; raise it (or check
    # https://console.groq.com/settings/billing) after upgrading to Dev
    # Tier. Set to 0 to disable proactive throttling entirely.
    groq_tpm_limit: int = field(default_factory=_env_int("GROQ_TPM_LIMIT", 8000))
    # Used to estimate an upcoming call's cost before Groq's actual
    # `usage.total_tokens` is known (i.e. for the very first calls in a
    # window). Real usage is recorded once a response comes back, so this
    # only affects how cautious the client is early on.
    groq_estimated_output_tokens: int = field(
        default_factory=_env_int("GROQ_ESTIMATED_OUTPUT_TOKENS", 900)
    )

    # --- Generation / validation behaviour ---
    max_regeneration_retries: int = field(
        default_factory=_env_int("MAX_REGENERATION_RETRIES", 2)
    )
    near_duplicate_similarity_threshold: float = field(
        default_factory=_env_float("NEAR_DUPLICATE_SIMILARITY_THRESHOLD", 0.90)
    )
    max_batch_count: int = field(default_factory=_env_int("MAX_BATCH_COUNT", 25))

    # Optional second-pass LLM relevance check. Off by default because it
    # adds one extra Groq call per batch.
    enable_llm_relevance_check: bool = field(
        default_factory=_env_bool("ENABLE_LLM_RELEVANCE_CHECK", False)
    )


settings = Settings()


def reload_settings() -> Settings:
    """
    Re-read every value from the current environment and return a fresh
    Settings. Used by tests, and by the Backend if it sets configuration
    after this module has been imported.
    """
    global settings
    settings = Settings()
    return settings
