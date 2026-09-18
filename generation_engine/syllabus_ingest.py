"""
Syllabus PDF-ingestion pipeline.

spec.md Section 8 lists the PDF-parsing approach for syllabus ingestion as an
open decision; this module is that decision. It turns a textbook's table-of-
contents (or, in a pinch, its chapter-heading pages) into the same JSON shape
`SyllabusIndex.from_json` already consumes (see syllabus.py's docstring):

    {"Science": {"chapters": ["Nutrition in Plants", "Force and Pressure"]}}

Design choice: **heuristic, regex-based line parsing, not layout/ML
extraction.** Indian state-board and NCERT textbook contents pages are
consistently line-per-chapter, usually "N. Title .... page" or "N. Title
page". A handful of regexes over `pypdf`'s plain-text extraction covers the
overwhelming majority of these cleanly, with zero system dependencies (no
poppler/tesseract to install across three different laptops) and zero extra
cost (no LLM call to parse a table of contents). spec.md already flags "how
much manual cleanup" as an open question for whichever approach was picked —
this one answers it by never writing straight to syllabus.json: `--dry-run`
(the CLI default) always shows you what it found before anything is written,
because textbook contents pages are not uniform enough to trust blindly.

This is why `ingest_syllabus.py` (the CLI) defaults to scanning only the
table-of-contents page range rather than the whole book: scanning every page
finds each chapter's own numbered heading too (good), but also matches
against every numbered *list item* in the body text of a chapter that
happens to contain one (bad — "3. Cell wall" inside a biology chapter about
cell structure looks identical to a TOC line). Pass --pages to point this
at just the contents pages; the whole-book fallback with no --pages exists
for textbooks whose contents page is unusable (e.g. scanned/no text layer)
and relies on --dry-run review to catch the false positives it will produce.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from .schemas import Subject
from .syllabus import _normalize_chapter

# Lines that are structurally identical to a numbered chapter entry but
# aren't one — front/back matter that shows up in almost every textbook's
# contents page. Matched against the normalized (lowercased, punctuation-
# stripped) title, so "Answers" and "ANSWERS." both match "answers".
_NON_CHAPTER_TITLES = {
    "contents",
    "content",
    "preface",
    "foreword",
    "introduction",
    "index",
    "appendix",
    "appendices",
    "glossary",
    "answers",
    "answer key",
    "answer keys",
    "bibliography",
    "references",
    "acknowledgements",
    "acknowledgments",
    "about the book",
    "about this book",
    "how to use this book",
    "syllabus",
    "curriculum",
    "notes",
}

# Tried in order; first match on a line wins. Each captures (number, title).
# Page-number-anchored patterns come first because they're the most specific
# (least likely to false-positive on ordinary numbered body text); the bare
# "N. Title" fallback comes last because it's the most permissive.
_LINE_PATTERNS = [
    # "1. Nutrition in Plants .......... 7"  (dot/dash leader + page number)
    re.compile(r"^\s*(\d{1,2})[.\)]\s+(.+?)\s*[.\-–—_]{3,}\s*\d{1,4}\s*$"),
    # "1. Nutrition in Plants          7"  (whitespace-only leader + page number)
    re.compile(r"^\s*(\d{1,2})[.\)]\s+(.+?)\s{2,}\d{1,4}\s*$"),
    # "1  Nutrition in Plants  7"  (no punctuation after the number at all)
    re.compile(r"^\s*(\d{1,2})\s{2,}(.+?)\s{2,}\d{1,4}\s*$"),
    # "Chapter 1: Nutrition in Plants" / "Unit 1 - Nutrition in Plants"
    re.compile(
        r"^\s*(?:chapter|unit)\s+(\d{1,2})\s*[:.\-–—]?\s+(.+?)\s*$",
        re.IGNORECASE,
    ),
    # "1. Nutrition in Plants"  (bare numbered line, no page number at all —
    # the common case on a chapter's own first page rather than a TOC)
    re.compile(r"^\s*(\d{1,2})[.\)]\s+(.+?)\s*$"),
]

_TRAILING_PUNCT = re.compile(r"[\s.\-–—_]+$")


def _clean_title(raw: str) -> str:
    return _TRAILING_PUNCT.sub("", raw).strip()


def extract_chapters_from_text(text: str) -> list[str]:
    """Parse chapter titles out of contents-page (or chapter-heading) text.

    Order-preserving, deduplicated (case/punctuation-insensitive, via the
    same `_normalize_chapter` the rest of the syllabus module uses so a
    chapter ingested here dedupes identically against one already in
    syllabus.json). Lines matching `_NON_CHAPTER_TITLES` are dropped.
    """
    seen: set[str] = set()
    chapters: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pattern in _LINE_PATTERNS:
            m = pattern.match(line)
            if not m:
                continue
            title = _clean_title(m.group(2))
            if not title or not re.search(r"[A-Za-z]", title):
                break  # matched the shape, but no usable title — don't fall through
            normalized = _normalize_chapter(title)
            if not normalized or normalized in _NON_CHAPTER_TITLES:
                break
            if normalized in seen:
                break
            seen.add(normalized)
            chapters.append(title)
            break
    return chapters


def _parse_page_range(pages: str | None, page_count: int) -> tuple[int, int]:
    """Parse a 1-indexed, inclusive '--pages' CLI value into a 0-indexed
    [start, end) slice range. None means the whole document."""
    if pages is None:
        return 0, page_count
    pages = pages.strip()
    if "-" in pages:
        start_s, end_s = pages.split("-", 1)
        start, end = int(start_s), int(end_s)
    else:
        start = end = int(pages)
    if start < 1 or end < start:
        raise ValueError(f"invalid --pages value: {pages!r}")
    return start - 1, min(end, page_count)


def extract_chapters_from_pdf(path: str | Path, pages: str | None = None) -> list[str]:
    """Extract chapter titles from a PDF's text layer.

    `pages` is a 1-indexed, inclusive range as a CLI-style string ("3-6" or
    "3"); None scans the whole document (see the module docstring for why
    that's the noisier option). Requires `pypdf` (pure-Python, no system
    dependencies) — install it via generation_engine/requirements.txt.

    Raises FileNotFoundError if `path` doesn't exist, and ValueError if the
    PDF has no extractable text layer (i.e. it's a scan) — pypdf will return
    empty strings for every page rather than raising in that case, so this
    checks explicitly and fails loudly instead of silently ingesting zero
    chapters.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover — import guard, not logic
        raise ImportError(
            "syllabus_ingest requires pypdf: pip install pypdf "
            "(already in generation_engine/requirements.txt)"
        ) from exc

    reader = PdfReader(str(path))
    start, end = _parse_page_range(pages, len(reader.pages))

    text_parts = []
    for page in reader.pages[start:end]:
        text_parts.append(page.extract_text() or "")
    text = "\n".join(text_parts)

    if not text.strip():
        raise ValueError(
            f"{path} has no extractable text in pages {start + 1}-{end} — "
            "likely a scanned PDF with no text layer. This pipeline doesn't "
            "do OCR; re-export the source or transcribe the contents page "
            "into backend/data/syllabus.json by hand instead."
        )

    return extract_chapters_from_text(text)


def merge_chapters(
    existing: dict,
    subject: Subject,
    new_chapters: list[str],
    mode: Literal["append", "replace"] = "append",
) -> tuple[dict, int, int]:
    """Merge `new_chapters` into `existing` (the raw syllabus.json dict) under
    `subject`. Dedupes the same way SyllabusIndex does, so re-running an
    ingest is idempotent.

    Returns (updated_dict, added_count, skipped_duplicate_count). Doesn't
    mutate `existing` in place — returns a new dict — so a caller can inspect
    the result before deciding to write it.
    """
    updated = dict(existing)
    entry = dict(updated.get(subject.value, {}))
    current: list[str] = list(entry.get("chapters", []))

    if mode == "replace":
        current = []

    seen = {_normalize_chapter(c) for c in current}
    added = 0
    skipped = 0
    for title in new_chapters:
        normalized = _normalize_chapter(title)
        if not normalized or normalized in seen:
            skipped += 1
            continue
        seen.add(normalized)
        current.append(title)
        added += 1

    entry["chapters"] = current
    updated[subject.value] = entry
    return updated, added, skipped
