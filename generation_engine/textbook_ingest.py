"""
Textbook PDF -> corpus JSON (see textbook.py for the format).

Pure-Python (pypdf), no OCR. Pipeline, in order:

  1. Read every page's text; strip running headers/footers and bare page
     numbers.
  2. Find chapters. First hit wins:
       a. explicit `chapters` titles passed by the caller (override),
       b. the PDF's own outline/bookmarks,
       c. a table-of-contents page (several "N. Title ..... page" lines),
       d. "Chapter/Unit/Lesson N" headings at the top of pages.
     TOC titles are located in the body by searching for the title near the top
     of a page, in order. A title that can't be found is reported in
     `warnings` and skipped — chapter boundaries are never invented.
  3. Split each chapter into sections ("1.2 Heading" lines) and then into
     passages of roughly `target_chars`, cut at sentence boundaries.

The output is a *draft to review*: `IngestResult.warnings` lists everything that
looked off (missing chapters, a likely non-Unicode Kannada text layer, chapters
with almost no text). Scanned PDFs have no text layer and are refused.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schemas import Subject
from .syllabus import _normalize_chapter
from .syllabus_ingest import _NON_CHAPTER_TITLES
from .textbook import CORPUS_VERSION, INTRO_SECTION

_KANNADA = re.compile(r"[\u0C80-\u0CFF]")
_PAGE_NUM_LINE = re.compile(r"^\s*(?:page\s*)?[-–]?\s*\d{1,4}\s*[-–]?\s*$", re.IGNORECASE)
_SECTION_HEADING = re.compile(r"^\s*(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)[.)]?\s+(\S.{2,90}?)\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")

_TOC_PATTERNS = [
    re.compile(r"^\s*(\d{1,2})[.)]?\s+(.+?)\s*[.\-–—_·…]{2,}\s*(\d{1,4})\s*$"),
    re.compile(r"^\s*(\d{1,2})[.)]\s+(.+?)\s{2,}(\d{1,4})\s*$"),
    re.compile(r"^\s*(?:chapter|unit|lesson)\s+(\d{1,2})\s*[:.\-–—]?\s+(.+?)\s+(\d{1,4})\s*$", re.IGNORECASE),
]
_TOP_HEADING = re.compile(r"^\s*(?:chapter|unit|lesson)\s+(\d{1,2})\b\s*[:.\-–—]?\s*(.*)$", re.IGNORECASE)


@dataclass
class IngestResult:
    corpus: dict
    chapters_found: int = 0
    passages: int = 0
    method: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# page cleaning
# ---------------------------------------------------------------------------

def _line_key(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def clean_pages(pages: list[str]) -> list[str]:
    """Drop running headers/footers (short lines repeated across many pages) and bare page numbers."""
    n = len(pages)
    counts: Counter[str] = Counter()
    for text in pages:
        for k in {_line_key(l) for l in text.splitlines() if l.strip()}:
            counts[k] += 1
    threshold = max(4, int(n * 0.35))
    cleaned: list[str] = []
    for text in pages:
        keep: list[str] = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                keep.append("")
                continue
            if _PAGE_NUM_LINE.match(s):
                continue
            if len(s) < 90 and counts[_line_key(s)] >= threshold and n >= 8:
                continue
            keep.append(s)
        cleaned.append("\n".join(keep))
    return cleaned


# ---------------------------------------------------------------------------
# chapter discovery
# ---------------------------------------------------------------------------

def toc_entries(text: str) -> list[tuple[str, int]]:
    """(title, printed page) for TOC-shaped lines, with strictly increasing page numbers."""
    out: list[tuple[str, int]] = []
    last = 0
    for line in text.splitlines():
        for pat in _TOC_PATTERNS:
            m = pat.match(line)
            if not m:
                continue
            title = re.sub(r"[\s.\-–—_·…]+$", "", m.group(2)).strip()
            page = int(m.group(3))
            norm = _normalize_chapter(title)
            if (
                title
                and re.search(r"[^\W\d_]", title)
                and norm not in _NON_CHAPTER_TITLES
                and page >= last
            ):
                out.append((title, page))
                last = page
            break
    return out


def find_toc(pages: list[str], scan: int = 20) -> tuple[list[str], int]:
    """Titles from the first run of pages that look like a table of contents; also the last TOC page index."""
    titles: list[str] = []
    last_idx = -1
    for i, text in enumerate(pages[:scan]):
        entries = toc_entries(text)
        if len(entries) >= 4:
            titles.extend(t for t, _ in entries)
            last_idx = i
        elif titles:
            break  # the contiguous TOC run ended
    seen: set[str] = set()
    uniq: list[str] = []
    for t in titles:
        k = _normalize_chapter(t)
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq, last_idx


def _locate_titles(
    pages: list[str], titles: list[str], first_page: int, warnings: list[str]
) -> list[tuple[str, int]]:
    """Find each title, in order, near the top of a page at or after the previous chapter start."""
    found: list[tuple[str, int]] = []
    cursor = first_page
    for title in titles:
        want = _normalize_chapter(title)
        short = " ".join(want.split()[:3])
        hit: Optional[int] = None
        for probe in (want, short):
            if not probe:
                continue
            for i in range(cursor, len(pages)):
                head = _normalize_chapter(" ".join(pages[i].strip().splitlines()[:6]))
                if probe in head:
                    hit = i
                    break
            if hit is not None:
                break
        if hit is None:
            warnings.append(f'chapter "{title}" is in the contents but its start page was not found; skipped')
            continue
        found.append((title, hit))
        cursor = hit + 1
    return found


def _scan_headings(pages: list[str]) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    seen_nums: set[int] = set()
    for i, text in enumerate(pages):
        lines = [l.strip() for l in text.splitlines() if l.strip()][:4]
        for j, line in enumerate(lines):
            m = _TOP_HEADING.match(line)
            if not m:
                continue
            num = int(m.group(1))
            if num in seen_nums:
                break
            title = m.group(2).strip() or (lines[j + 1] if j + 1 < len(lines) else "")
            title = re.sub(r"[\s.\-–—_]+$", "", title)
            if title:
                seen_nums.add(num)
                found.append((title, i))
            break
    return found


def discover_chapters(
    pages: list[str],
    outline: Optional[list[tuple[str, int]]] = None,
    chapters: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> tuple[list[tuple[str, int]], str]:
    """Returns ([(title, start page index)], method)."""
    warnings = warnings if warnings is not None else []
    if chapters:
        _, toc_last = find_toc(pages)
        return _locate_titles(pages, chapters, toc_last + 1, warnings), "explicit chapter list"
    if outline:
        usable = [
            (t.strip(), p)
            for t, p in outline
            if t and _normalize_chapter(t) not in _NON_CHAPTER_TITLES and 0 <= p < len(pages)
        ]
        if len(usable) >= 2:
            return usable, "PDF outline"
    titles, toc_last = find_toc(pages)
    if len(titles) >= 2:
        return _locate_titles(pages, titles, toc_last + 1, warnings), "table of contents"
    headings = _scan_headings(pages)
    if headings:
        return headings, "chapter headings"
    return [], "none"


# ---------------------------------------------------------------------------
# sections & passages
# ---------------------------------------------------------------------------

def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = [(INTRO_SECTION, [])]
    for line in text.splitlines():
        m = _SECTION_HEADING.match(line)
        if m and not re.search(r"[.!?]$", m.group(2)) and len(m.group(2).split()) <= 12:
            sections.append((f"{m.group(1)} {m.group(2).strip()}", []))
        else:
            sections[-1][1].append(line)
    return [(t, "\n".join(ls).strip()) for t, ls in sections if "\n".join(ls).strip()]


def _chunk(text: str, target: int, hard_max: int) -> list[str]:
    flat = re.sub(r"[ \t]+", " ", re.sub(r"\n+", "\n", text)).strip()
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(flat.replace("\n", " ")) if s.strip()]
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        while len(s) > hard_max:  # a runaway "sentence" (formula dump, table)
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(s[:hard_max])
            s = s[hard_max:]
        if cur and len(cur) + 1 + len(s) > hard_max:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
        if len(cur) >= target:
            chunks.append(cur)
            cur = ""
    if cur:
        if chunks and len(cur) < target // 3:
            chunks[-1] = f"{chunks[-1]} {cur}"
        else:
            chunks.append(cur)
    return chunks


def build_passages(
    chapter_text: str, id_prefix: str, target_chars: int = 900, min_chars: int = 150
) -> list[dict]:
    passages: list[dict] = []
    k = 0
    for section, body in _split_sections(chapter_text):
        for chunk in _chunk(body, target_chars, int(target_chars * 1.4)):
            if len(re.sub(r"\s+", "", chunk)) < min_chars:
                continue
            k += 1
            passages.append({"id": f"{id_prefix}-p{k:03d}", "section": section, "text": chunk})
    return passages


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------

def _slug(subject: Subject) -> str:
    return subject.value.lower().replace(" ", "-")


def build_corpus_dict(
    pages: list[str],
    subject: Subject,
    grade: int,
    part: str = "",
    medium: str = "English",
    source_file: str = "",
    sha256: str = "",
    outline: Optional[list[tuple[str, int]]] = None,
    chapters: Optional[list[str]] = None,
    target_chars: int = 900,
) -> IngestResult:
    if not any(p.strip() for p in pages):
        raise ValueError(
            "no extractable text — this looks like a scanned PDF. This pipeline does "
            "not OCR; use a text-layer PDF (e.g. the e-textbook from KTBS) instead."
        )
    warnings: list[str] = []
    cleaned = clean_pages(pages)
    starts, method = discover_chapters(cleaned, outline, chapters, warnings)
    if not starts:
        raise ValueError(
            "could not find any chapters (no explicit list, outline, contents page or "
            "'Chapter N' headings). Pass the chapter titles explicitly."
        )
    starts = sorted(starts, key=lambda t: t[1])

    sample = "".join(cleaned[:30])
    letters = re.findall(r"[^\W\d_]", sample)
    if (subject == Subject.KANNADA or medium.lower() == "kannada") and letters:
        ratio = len(_KANNADA.findall(sample)) / len(letters)
        if ratio < 0.3:
            warnings.append(
                "expected Kannada script but the text layer is mostly non-Kannada "
                f"({ratio:.0%}); the PDF likely uses a legacy font and extracts as garbage"
            )

    prefix_base = f"{_slug(subject)}-{grade}{('p' + part) if part else ''}"
    chapter_dicts: list[dict] = []
    total = 0
    for idx, (title, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(cleaned)
        number = idx + 1
        text = "\n".join(cleaned[start:end])
        passages = build_passages(text, f"{prefix_base}-c{number:02d}", target_chars)
        if not passages:
            warnings.append(f'chapter "{title}" produced no passages (pages {start + 1}-{end}); skipped')
            continue
        total += len(passages)
        chapter_dicts.append(
            {"number": number, "title": title, "pages": [start + 1, end], "passages": passages}
        )
        if sum(len(p["text"]) for p in passages) < 600:
            warnings.append(f'chapter "{title}" has very little text ({len(passages)} passage(s)); check the PDF')

    corpus = {
        "version": CORPUS_VERSION,
        "subject": subject.value,
        "grade": grade,
        "part": part,
        "medium": medium,
        "source_file": source_file,
        "sha256": sha256,
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extraction": method,
        "chapters": chapter_dicts,
    }
    return IngestResult(
        corpus=corpus,
        chapters_found=len(chapter_dicts),
        passages=total,
        method=method,
        warnings=warnings,
    )


def ingest_pdf(
    path: str | Path,
    subject: Subject,
    grade: int,
    part: str = "",
    medium: str = "English",
    chapters: Optional[list[str]] = None,
    target_chars: int = 900,
) -> IngestResult:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    from pypdf import PdfReader  # pure-Python; see requirements.txt

    reader = PdfReader(str(path))
    pages = [(p.extract_text() or "") for p in reader.pages]

    outline: list[tuple[str, int]] = []
    try:
        for item in reader.outline:
            if isinstance(item, list):  # nested children — top level only
                continue
            outline.append((str(item.title), reader.get_destination_page_number(item)))
    except Exception:  # malformed/absent outline is routine
        outline = []

    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return build_corpus_dict(
        pages, subject, grade, part, medium, path.name, sha, outline, chapters, target_chars
    )
