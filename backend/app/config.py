"""
Backend runtime configuration.

Read from the environment / `.env` (see backend/.env.example). Generation
settings (Groq key, model, retry budget, duplicate threshold) are NOT
duplicated here — those belong to Module A and are read by
`generation_engine.config.Settings`. This module only owns Module B's own
concerns: database, export, CORS, caching.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

# Export every value from both .env files into os.environ as well.
# pydantic-settings only reads them into `Settings` below; Module A
# (generation_engine.config) reads GROQ_API_KEY etc. straight from os.environ
# and would otherwise only find a key that sits in a .env next to *its own*
# package. backend/.env is loaded first so it wins over the repo-root .env
# (override=False keeps real environment variables on top of both).
try:  # python-dotenv is a hard dependency, but never crash config over it
    from dotenv import load_dotenv

    for _env_file in (BACKEND_DIR / ".env", REPO_ROOT / ".env"):
        load_dotenv(_env_file, override=False)
except ImportError:  # pragma: no cover
    pass


def _anchor(path: Path) -> Path:
    """
    Make a relative path from .env independent of the working directory.

    backend/.env.example uses paths like ./data/syllabus.json, written as if
    uvicorn is started from backend/. The frontend README starts it from the
    repo root instead (uvicorn backend.app.main:app), where that path does not
    exist: the syllabus silently failed to load, no chapters were seeded, the
    chapter dropdown stayed empty and the Generate button stayed disabled.
    Try the CWD first (keeps existing setups working), then backend/, then the
    repo root.
    """
    if path.is_absolute():
        return path
    for base in (Path.cwd(), BACKEND_DIR, REPO_ROOT):
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate
    return (BACKEND_DIR / path).resolve()


@dataclass(frozen=True)
class Rule:
    limit: int
    window: float  # seconds


@lru_cache(maxsize=64)
def parse_rule(spec: str) -> Rule:
    """'10/60' -> at most 10 hits per 60 seconds."""
    try:
        count, seconds = spec.strip().split("/")
        rule = Rule(int(count), float(seconds))
    except ValueError:
        raise ValueError(
            f"invalid rate limit {spec!r}: expected '<requests>/<seconds>', e.g. '10/60'"
        ) from None
    if rule.limit < 1 or rule.window <= 0:
        raise ValueError(f"invalid rate limit {spec!r}: both numbers must be positive")
    return rule


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
    # Create missing tables at startup. Always on for SQLite (there is no
    # separate migration step for a local dev database). For PostgreSQL, leave
    # it off and run `alembic upgrade head`, or set this to true for a quick start.
    auto_create_tables: bool = Field(default=False, alias="AUTO_CREATE_TABLES")

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
    # --- Textbook corpus (strict Karnataka State Board mode) ---
    # Folder of corpus JSON produced by scripts/ingest_textbooks.py from the
    # KTBS textbook PDFs. Chapters, grades and topics are derived from these;
    # questions are written from their text.
    textbooks_dir: Path = Field(
        default=BACKEND_DIR / "data" / "textbooks", alias="TEXTBOOKS_DIR"
    )
    # true  -> generate ONLY for (subject, grade) pairs with an ingested textbook;
    #          the bundled syllabus.json is ignored (nothing hardcoded).
    # false -> textbooks are used where present; anything else falls back to
    #          syllabus.json / free chapter names.
    require_textbook: bool = Field(default=False, alias="REQUIRE_TEXTBOOK")

    # --- Figures (diagrams attached to questions / answer keys) ---
    # Uploaded images are re-encoded and stored here, one file per figure.
    # Local disk, like EXPORT_DIR: on a multi-instance deployment move it to
    # object storage (only services/figures.py touches the filesystem).
    figure_dir: Path = Field(default=REPO_ROOT / "var" / "figures", alias="FIGURE_DIR")
    # Largest upload accepted, in bytes (default 5 MB).
    max_figure_bytes: int = Field(default=5 * 1024 * 1024, alias="MAX_FIGURE_BYTES", ge=1024)
    # Most figures described to the model in one "generate with figures" call.
    # Each adds a few lines to the prompt, and fewer figures per call keeps the
    # questions from spreading too thin across them.
    max_generation_figures: int = Field(
        default=6, alias="MAX_GENERATION_FIGURES", ge=1, le=20
    )
    # auto -> WeasyPrint if installed (correct Kannada/Indic shaping via
    # HarfBuzz), else ReportLab. See services/export/renderer.py.
    pdf_renderer: Literal["auto", "weasyprint", "reportlab", "fpdf"] = Field(
        default="auto", alias="PDF_RENDERER"
    )

    # --- Syllabus seed data (optional; Module A's SyllabusIndex JSON shape) ---
    # Defaults to the bundled chapter list so the chapter dropdown is populated
    # even when SYLLABUS_JSON_PATH isn't set in .env. Set it to an empty value
    # (SYLLABUS_JSON_PATH=) to run without a syllabus.
    syllabus_json_path: Path | None = Field(
        default=BACKEND_DIR / "data" / "syllabus.json", alias="SYLLABUS_JSON_PATH"
    )

    # --- Practice mode ---
    # If a practice session can't be filled from stored questions, generate the
    # shortfall on demand instead of returning a short set.
    practice_generate_shortfall: bool = Field(
        default=True, alias="PRACTICE_GENERATE_SHORTFALL"
    )

    # --- Auth (JWT bearer tokens) ---
    # HS256 signing key. Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(48))"
    # If left empty, a random per-process key is used: fine for local
    # development, but every restart signs everyone out and multiple workers
    # would disagree — so set JWT_SECRET in any real deployment.
    jwt_secret: str = Field(default="", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60 * 24 * 7, alias="ACCESS_TOKEN_EXPIRE_MINUTES", ge=1
    )

    # --- Password reset ---
    # A reset link is a signed token valid for this many minutes. It is single-use:
    # it is bound to the current password hash, so it dies as soon as the password changes.
    password_reset_expire_minutes: int = Field(
        default=30, alias="PASSWORD_RESET_EXPIRE_MINUTES", ge=1
    )
    # Where the reset link points (the frontend's origin, no trailing slash).
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    # Outgoing email. With SMTP_HOST empty, no email is sent: the reset link is
    # written to the backend log instead (fine for local development).
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="KRIES <no-reply@localhost>", alias="SMTP_FROM")
    # starttls (port 587) | ssl (port 465) | none
    smtp_security: Literal["starttls", "ssl", "none"] = Field(
        default="starttls", alias="SMTP_SECURITY"
    )

    # --- Rate limiting (in-memory, per process; see app/ratelimit.py) ---
    # Each limit is "<requests>/<seconds>", e.g. "10/60" = 10 requests per minute.
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    # Every /api request, per signed-in user (or per IP when not signed in).
    rate_limit_default: str = Field(default="120/60", alias="RATE_LIMIT_DEFAULT")
    # POST /auth/login, per IP.
    rate_limit_login: str = Field(default="10/60", alias="RATE_LIMIT_LOGIN")
    # POST /auth/signup, per IP.
    rate_limit_signup: str = Field(default="5/3600", alias="RATE_LIMIT_SIGNUP")
    # POST /auth/forgot-password and /auth/reset-password, per IP.
    rate_limit_password_reset: str = Field(
        default="5/900", alias="RATE_LIMIT_PASSWORD_RESET"
    )
    # Calls that can reach the LLM (POST /generate, POST /practice/sessions), per user.
    # One "Mixed" generation in the UI is up to 9 calls, so keep this generous.
    rate_limit_generate: str = Field(default="30/60", alias="RATE_LIMIT_GENERATE")
    # POST /export/{id}, per user.
    rate_limit_export: str = Field(default="10/60", alias="RATE_LIMIT_EXPORT")
    # POST /figures (image uploads), per user.
    rate_limit_upload: str = Field(default="20/60", alias="RATE_LIMIT_UPLOAD")
    # Wrong passwords allowed per (IP, email) before that pair is locked out.
    login_max_failures: str = Field(default="5/900", alias="LOGIN_MAX_FAILURES")
    # Read the client IP from X-Forwarded-For. Turn on ONLY behind a reverse
    # proxy you control (Render, Nginx...): otherwise clients can fake their IP
    # and dodge the per-IP limits.
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")

    @field_validator(
        "rate_limit_default",
        "rate_limit_login",
        "rate_limit_signup",
        "rate_limit_password_reset",
        "rate_limit_generate",
        "rate_limit_export",
        "rate_limit_upload",
        "login_max_failures",
        mode="after",
    )
    @classmethod
    def _valid_rate_limit(cls, v: str) -> str:
        parse_rule(v)  # raises ValueError with a readable message
        return v

    @field_validator(
        "syllabus_json_path", "export_dir", "figure_dir", "textbooks_dir", mode="after"
    )
    @classmethod
    def anchor_relative_paths(cls, v: Path | None) -> Path | None:
        return _anchor(v) if v is not None else None

    @field_validator("syllabus_json_path", mode="before")
    @classmethod
    def blank_syllabus_path_means_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def jwt_secret_is_ephemeral(self) -> bool:
        return not self.jwt_secret.strip()

    @property
    def should_create_tables(self) -> bool:
        return self.auto_create_tables or self.is_sqlite

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
