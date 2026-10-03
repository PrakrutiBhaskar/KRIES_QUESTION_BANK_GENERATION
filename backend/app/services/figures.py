"""
Figures: diagrams that can be attached to a question and printed in the paper
or in the answer key.

Everything that touches the image files lives here, so moving storage from local
disk to object storage later only changes this module (the PDF renderers go
through `read_figure_bytes`, never through a path of their own).

Uploads are *never* stored as received. The bytes are sniffed by Pillow (the
client's file name and Content-Type are ignored), decoded, flattened onto a
white background, stripped of metadata (EXIF, GPS, embedded profiles), scaled
down to a print-sensible size and re-encoded as PNG or JPEG. That is what makes
it safe to embed the result in a PDF, and it is why SVG is not accepted: an SVG
is code, not pixels.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import FigureContext, Subject

from ..config import settings
from ..errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
)
from ..models import Figure, Question

logger = logging.getLogger("backend.figures")

# Formats we are willing to decode. GIF/WebP are converted to PNG on the way in;
# anything else (SVG, TIFF, PDF, ...) is rejected.
ACCEPTED_FORMATS = {"PNG", "JPEG", "GIF", "WEBP"}
# Longest side kept, in pixels. A figure is printed at most ~178 mm wide, so
# 2400 px is roughly 340 dpi: sharp on paper, and keeps PDFs small.
MAX_SIDE_PX = 2400
# Refuse to even decode anything bigger than this (decompression-bomb guard).
MAX_PIXELS = 30_000_000
MAX_CAPTION_LEN = 300


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    mime: str
    ext: str
    width: int
    height: int


# --- storage ---------------------------------------------------------------


def figure_dir() -> Path:
    path = Path(settings.figure_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def figure_path(figure: Figure) -> Path:
    return figure_dir() / figure.filename


def read_figure_bytes(figure: Figure | None) -> bytes | None:
    """The stored image, or None if there is no figure or its file has gone.

    Renderers call this so that a missing file degrades to "no figure" (with a
    warning in the log) instead of failing the whole export.
    """
    if figure is None:
        return None
    try:
        return figure_path(figure).read_bytes()
    except OSError as exc:
        logger.warning("Figure %s is missing on disk (%s); exporting without it.", figure.id, exc)
        return None


def _write_atomically(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# --- image handling --------------------------------------------------------


def process_upload(data: bytes) -> ProcessedImage:
    """Validate and normalise an uploaded image. Raises BadRequestError."""
    if not data:
        raise BadRequestError("The uploaded file is empty.", error="invalid_image")
    try:
        img = Image.open(BytesIO(data))
        fmt = (img.format or "").upper()
        width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BadRequestError(
            "That file is not a readable image. Upload a PNG or JPEG.",
            error="invalid_image",
        ) from exc

    if fmt not in ACCEPTED_FORMATS:
        raise BadRequestError(
            "Unsupported image type. Upload a PNG or JPEG (GIF and WebP are converted).",
            error="invalid_image",
        )
    if width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise BadRequestError(
            f"Image is too large to process ({width} x {height} px). "
            "Resize it below about 30 megapixels and try again.",
            error="invalid_image",
        )

    # Decode now, so a truncated/corrupt file fails here. WeasyPrint switches
    # Pillow's LOAD_TRUNCATED_IMAGES on for the whole process when it is
    # imported, which would let half an image through, so force it off for this
    # one decode instead of depending on which PDF backend happens to be loaded.
    previous = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        img.load()
        if fmt == "JPEG":  # photos carry an EXIF rotation; PNG/GIF/WebP don't
            img = ImageOps.exif_transpose(img)
    except (OSError, ValueError, SyntaxError) as exc:
        raise BadRequestError(
            "The image file is damaged and could not be decoded.", error="invalid_image"
        ) from exc
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = previous

    as_jpeg = fmt == "JPEG"
    img = _flatten(img, keep_gray=True)
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX), Image.Resampling.LANCZOS)

    buf = BytesIO()
    if as_jpeg:
        img.save(buf, "JPEG", quality=90, optimize=True)
        mime, ext = "image/jpeg", "jpg"
    else:
        img.save(buf, "PNG", optimize=True)
        mime, ext = "image/png", "png"
    return ProcessedImage(buf.getvalue(), mime, ext, img.width, img.height)


def _flatten(img: Image.Image, *, keep_gray: bool) -> Image.Image:
    """Composite transparency onto white and reduce to plain L or RGB.

    Transparent regions would otherwise print black in some PDF viewers, and
    palette/1-bit/16-bit modes are not handled consistently by all renderers.
    """
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if has_alpha:
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    if img.mode == "L" and keep_gray:
        return img
    if img.mode == "RGB":
        return img
    if img.mode in ("1", "I;16", "I", "F") and keep_gray:
        return img.convert("L")
    return img.convert("RGB")


# --- metadata (what question generation works from) --------------------------

MAX_META_LEN = 120  # chapter / topic
MAX_LABELS = 30
MAX_LABEL_LEN = 80


def clean_short_text(value: str | None, *, field: str) -> str | None:
    """Tidy a chapter/topic value; blank becomes None."""
    text = " ".join((value or "").split())
    if len(text) > MAX_META_LEN:
        raise BadRequestError(f"{field.capitalize()} must be at most {MAX_META_LEN} characters.")
    return text or None


def clean_subject(value: str | None) -> str | None:
    """The canonical subject name (\"Social Science\"), or None when blank."""
    text = " ".join((value or "").split())
    if not text:
        return None
    for subject in Subject:
        if subject.value.lower() == text.lower():
            return subject.value
    raise BadRequestError(
        f"Unknown subject \"{text}\". Use one of: {', '.join(s.value for s in Subject)}.",
        error="invalid_subject",
    )


def clean_labels(value: list[str] | str | None) -> list[str]:
    """Labelled parts as a tidy list of entries like \"A: nucleus\".

    Accepts a list, a JSON array in a string, or one entry per line (what a
    multipart form field or a textarea sends). Blank entries are dropped and
    repeats (ignoring case) are kept once, in order.
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        items: list = []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError as exc:
                raise BadRequestError("Labels must be a list, or one label per line.") from exc
            if not isinstance(parsed, list):
                raise BadRequestError("Labels must be a list, or one label per line.")
            items = parsed
        else:
            items = text.splitlines()
    else:
        items = list(value)

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        entry = " ".join(str(item).split())
        if not entry or entry.lower() in seen:
            continue
        if len(entry) > MAX_LABEL_LEN:
            raise BadRequestError(f"Each label must be at most {MAX_LABEL_LEN} characters.")
        seen.add(entry.lower())
        cleaned.append(entry)
    if len(cleaned) > MAX_LABELS:
        raise BadRequestError(f"A figure can have at most {MAX_LABELS} labels.")
    return cleaned


def has_metadata(figure: Figure) -> bool:
    """Whether there is anything to write questions from (a caption or labels)."""
    return bool((figure.caption or "").strip() or figure.labels)


def to_context(figure: Figure) -> FigureContext:
    """The text-only description handed to the generation engine."""
    return FigureContext(
        id=str(figure.id),
        caption=figure.caption or "",
        labels=list(figure.labels or []),
        topic=figure.topic or "",
    )


# --- CRUD ------------------------------------------------------------------


def clean_caption(caption: str | None) -> str:
    text = " ".join((caption or "").split())
    if len(text) > MAX_CAPTION_LEN:
        raise BadRequestError(f"Caption must be at most {MAX_CAPTION_LEN} characters.")
    return text


async def create_figure(
    session: AsyncSession,
    raw: bytes,
    *,
    caption: str | None,
    uploaded_by: uuid.UUID,
    subject: str | None = None,
    chapter: str | None = None,
    topic: str | None = None,
    labels: list[str] | str | None = None,
) -> Figure:
    if len(raw) > settings.max_figure_bytes:
        raise _too_large()
    processed = process_upload(raw)
    caption = clean_caption(caption)
    # Validate the metadata before anything is written to disk.
    subject = clean_subject(subject)
    chapter = clean_short_text(chapter, field="chapter")
    topic = clean_short_text(topic, field="topic")
    label_list = clean_labels(labels)

    figure_id = uuid.uuid4()
    filename = f"{figure_id}.{processed.ext}"
    path = figure_dir() / filename
    _write_atomically(path, processed.data)
    try:
        figure = Figure(
            id=figure_id,
            owner_id=uploaded_by,
            filename=filename,
            mime=processed.mime,
            width=processed.width,
            height=processed.height,
            size_bytes=len(processed.data),
            caption=caption,
            subject=subject,
            chapter=chapter,
            topic=topic,
            labels=label_list,
        )
        session.add(figure)
        await session.flush()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return figure


def _too_large() -> PayloadTooLargeError:
    limit_mb = settings.max_figure_bytes / (1024 * 1024)
    return PayloadTooLargeError(f"Image is larger than the {limit_mb:g} MB limit.")


async def get_figure(session: AsyncSession, figure_id: uuid.UUID) -> Figure:
    figure = await session.get(Figure, figure_id)
    if figure is None:
        raise NotFoundError(f"Figure {figure_id} not found.")
    return figure


async def list_figures(
    session: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
    subject: str | None = None,
    chapter: str | None = None,
) -> tuple[list[Figure], int]:
    base = select(Figure)
    if subject:
        base = base.where(Figure.subject == subject)
    if chapter:
        base = base.where(func.lower(Figure.chapter) == chapter.lower())
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        await session.scalars(
            base.order_by(Figure.created_at.desc(), Figure.id).limit(limit).offset(offset)
        )
    ).all()
    return list(rows), int(total)


async def update_metadata(
    session: AsyncSession, figure_id: uuid.UUID, changes: dict
) -> Figure:
    """Apply the fields present in `changes` (caption, subject, chapter, topic, labels).

    Everything is validated before anything is assigned, so a bad value leaves
    the figure untouched. An explicit null/empty value clears that field.
    """
    figure = await get_figure(session, figure_id)
    updates: dict = {}
    if "caption" in changes:
        updates["caption"] = clean_caption(changes["caption"])
    if "subject" in changes:
        updates["subject"] = clean_subject(changes["subject"])
    if "chapter" in changes:
        updates["chapter"] = clean_short_text(changes["chapter"], field="chapter")
    if "topic" in changes:
        updates["topic"] = clean_short_text(changes["topic"], field="topic")
    if "labels" in changes:
        updates["labels"] = clean_labels(changes["labels"])
    for key, value in updates.items():
        setattr(figure, key, value)
    await session.flush()
    return figure


async def usage_count(session: AsyncSession, figure_id: uuid.UUID) -> int:
    """How many live questions print this figure (in the paper or the key)."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Question)
            .where(
                Question.is_active.is_(True),
                (Question.figure_id == figure_id) | (Question.answer_figure_id == figure_id),
            )
        )
        or 0
    )


async def delete_figure(session: AsyncSession, figure_id: uuid.UUID) -> None:
    """Delete a figure from the library, unless a live question still uses it.

    Refusing (409) rather than silently detaching keeps papers that already
    contain the question from losing their diagram behind the admin's back.
    """
    figure = await get_figure(session, figure_id)
    in_use = await usage_count(session, figure_id)
    if in_use:
        raise ConflictError(
            f"This figure is attached to {in_use} question{'s' if in_use != 1 else ''}. "
            "Remove it from them first.",
            error="figure_in_use",
        )
    # Discarded (soft-deleted) questions may still point at it. SQLite does not
    # enforce ON DELETE SET NULL by default, so clear those links explicitly.
    await session.execute(
        update(Question).where(Question.figure_id == figure_id).values(figure_id=None)
    )
    await session.execute(
        update(Question)
        .where(Question.answer_figure_id == figure_id)
        .values(answer_figure_id=None)
    )
    path = figure_path(figure)
    await session.delete(figure)
    await session.flush()
    path.unlink(missing_ok=True)


async def resolve_attachable(session: AsyncSession, figure_id: uuid.UUID) -> Figure:
    """A library figure someone wants to attach to a question.

    The library is shared (administrators add to it, everyone uses it), so any
    existing figure can be attached; a missing one is a 404.
    """
    return await get_figure(session, figure_id)


# --- picking figures for generation ----------------------------------------


async def _usage_counts(session: AsyncSession, figure_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not figure_ids:
        return {}
    rows = await session.execute(
        select(Question.figure_id, func.count())
        .where(Question.is_active.is_(True), Question.figure_id.in_(figure_ids))
        .group_by(Question.figure_id)
    )
    return {fid: int(n) for fid, n in rows.all()}


async def library_figures_for_generation(
    session: AsyncSession,
    *,
    subject: str,
    chapter: str,
    topic: str | None,
    limit: int,
) -> list[Figure]:
    """Library figures tagged with this subject and chapter, ready to write from.

    A figure qualifies if it has a caption or labels. When a `topic` is given,
    figures tagged with a different topic are left out; figures with no topic
    count as chapter-wide and stay in. At most `limit` come back, the ones used
    by the fewest questions first (newest first among ties), so repeated
    generation rotates through the library instead of reusing the same few.
    """
    rows = (
        await session.scalars(
            select(Figure)
            .where(
                Figure.subject == subject,
                func.lower(Figure.chapter) == chapter.strip().lower(),
            )
            .order_by(Figure.created_at.desc(), Figure.id)
        )
    ).all()
    wanted = (topic or "").strip().lower()
    eligible = [
        f
        for f in rows
        if has_metadata(f)
        and (not wanted or not (f.topic or "").strip() or f.topic.strip().lower() == wanted)
    ]
    usage = await _usage_counts(session, [f.id for f in eligible])
    eligible.sort(key=lambda f: usage.get(f.id, 0))  # stable: newest-first kept on ties
    return eligible[:limit]


async def resolve_for_generation(
    session: AsyncSession, figure_ids: list[uuid.UUID], *, limit: int
) -> list[Figure]:
    """The exact library figures a caller named; each must have something to write from."""
    if len(figure_ids) > limit:
        raise BadRequestError(
            f"Choose at most {limit} figures per request, got {len(figure_ids)}.",
            error="too_many_figures",
        )
    figures: list[Figure] = []
    for figure_id in figure_ids:
        figure = await resolve_attachable(session, figure_id)
        if not has_metadata(figure):
            raise BadRequestError(
                f"Figure {figure_id} has no caption or labelled parts, so there is nothing "
                "to write questions from. Add a caption or labels to it first.",
                error="figure_has_no_metadata",
            )
        figures.append(figure)
    return figures


# --- layout shared by all three PDF renderers ------------------------------

# Pixels are assumed to be at this density when deciding how big to print a
# figure, so a small image is not stretched into a blurry full-width block.
BASE_DPI = 150
MM_PER_INCH = 25.4
# Print box for a figure inside the question column / answer key (A4, 16 mm
# side margins, text indented ~8 mm), and a height cap so one figure can never
# fill a page.
MAX_FIGURE_WIDTH_MM = 120.0
MAX_FIGURE_HEIGHT_MM = 70.0


def fit_size_mm(width_px: int, height_px: int) -> tuple[float, float]:
    """Printed (width, height) in mm: natural size at BASE_DPI, shrunk to fit."""
    w = width_px * MM_PER_INCH / BASE_DPI
    h = height_px * MM_PER_INCH / BASE_DPI
    scale = min(1.0, MAX_FIGURE_WIDTH_MM / w, MAX_FIGURE_HEIGHT_MM / h)
    return round(w * scale, 2), round(h * scale, 2)


def loaded_figure(question: Any, attr: str) -> Figure | None:
    """`question.figure` / `.answer_figure`, tolerant of fakes and unloaded rows."""
    return getattr(question, attr, None)


def answer_key_figure(question: Any) -> Figure | None:
    """The diagram to print in the answer key for a question.

    An explicit answer figure wins. Otherwise the question's own figure is used:
    generated questions are saved with `figure` only, so without this fallback
    the answer key would never show a diagram for them.
    """
    return loaded_figure(question, "answer_figure") or loaded_figure(question, "figure")
