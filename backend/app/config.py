"""
Backend runtime configuration.

Read from the environment / `.env` (see backend/.env.example). Generation
settings (Groq key, model, retry budget, duplicate threshold) are NOT
duplicated here — those belong to Module A and are read by
`generation_engine.config.Settings`. This module only owns Module B's own
concerns: database, export, CORS, caching.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Question Bank Generator API"
    api_prefix: str = "/api/v1"
    debug: bool = Field(default=False, alias="DEBUG")

    # --- Database ---
    # api-contract.md / ADR 4: PostgreSQL. Async driver (asyncpg) because the
    # generation path awaits Groq calls and we don't want to block the loop.
    database_url: str = Field(
        default="postgresql+asyncpg://localhost:5432/question_bank_db",
        alias="DATABASE_URL",
    )
    db_echo: bool = Field(default=False, alias="DB_ECHO")

    # --- CORS (React Native web target hits this from a browser origin) ---
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["*"], alias="CORS_ORIGINS"
    )

    # --- Generation caching (spec.md Module B: "avoid regenerating identical
    #     requests; store generated questions for reuse") ---
    enable_generation_cache: bool = Field(
        default=True, alias="ENABLE_GENERATION_CACHE"
    )

    # --- Export ---
    export_dir: Path = Field(default=REPO_ROOT / "var" / "exports", alias="EXPORT_DIR")
    # Used to build the absolute `download_url` returned by POST /export/{id}.
    public_base_url: str = Field(
        default="http://localhost:8000", alias="PUBLIC_BASE_URL"
    )
    # auto -> WeasyPrint if installed (correct Kannada/Indic shaping via
    # HarfBuzz), else ReportLab. See services/export/renderer.py.
    pdf_renderer: Literal["auto", "weasyprint", "reportlab"] = Field(
        default="auto", alias="PDF_RENDERER"
    )

    # --- Syllabus seed data (optional; Module A's SyllabusIndex JSON shape) ---
    syllabus_json_path: Path | None = Field(default=None, alias="SYLLABUS_JSON_PATH")

    # --- Practice mode ---
    # If a practice session can't be filled from stored questions, generate the
    # shortfall on demand instead of returning a short set.
    practice_generate_shortfall: bool = Field(
        default=True, alias="PRACTICE_GENERATE_SHORTFALL"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
