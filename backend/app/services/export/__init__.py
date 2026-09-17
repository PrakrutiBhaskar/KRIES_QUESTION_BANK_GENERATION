"""
Export service — compiles a paper into a downloadable PDF.

api-contract.md returns `{"download_url": "..."}` rather than the PDF bytes,
so the file is written to EXPORT_DIR and served back through
`GET /api/v1/export/files/{filename}`. That keeps the React Native client's
job identical on web and Android: both get a URL to hand to a download or
share intent (ADR 1's "platform-specific behaviour behind a shared
interface").

EXPORT_DIR is local disk, which is fine for a single instance and for Render.
On multi-instance AWS this should become S3 with a presigned URL — only
`_write` and `public_url` would change.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from ...config import settings
from ...errors import NotFoundError
from .html import render_paper_html
from .renderer import active_renderer, render_pdf

logger = logging.getLogger("backend.export")

_SLUG = re.compile(r"[^a-z0-9]+")
# Filenames are server-generated, but this guards the download route against
# a traversal attempt (`../../etc/passwd`) reaching the filesystem.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.pdf$")


def _slugify(text: str, *, limit: int = 60) -> str:
    slug = _SLUG.sub("-", text.strip().lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "paper"


def export_dir() -> Path:
    path = Path(settings.export_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_url(filename: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}{settings.api_prefix}/export/files/{filename}"


def resolve_download(filename: str) -> Path:
    if not _SAFE_FILENAME.match(filename):
        raise NotFoundError("No such export.")
    path = export_dir() / filename
    if not path.is_file():
        raise NotFoundError("This export has expired or was never created.")
    return path


def export_paper(paper) -> tuple[Path, int]:
    """Render `paper` to a PDF on disk. Returns (path, size_bytes)."""
    pdf_bytes = render_pdf(paper)

    # The uuid suffix keeps re-exports of the same paper from overwriting a
    # URL the client may still be downloading.
    filename = f"{_slugify(paper.title)}-{uuid.uuid4().hex[:8]}.pdf"
    path = export_dir() / filename
    path.write_bytes(pdf_bytes)

    logger.info(
        "Exported paper %s (%d questions) via %s -> %s (%d bytes)",
        paper.id,
        len(paper.items),
        active_renderer(),
        filename,
        len(pdf_bytes),
    )
    return path, len(pdf_bytes)


__all__ = [
    "active_renderer",
    "export_dir",
    "export_paper",
    "public_url",
    "render_paper_html",
    "render_pdf",
    "resolve_download",
]
