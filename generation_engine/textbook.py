"""
Textbook corpus — the Karnataka State Board (KTBS) textbooks as data.

This is what makes generation textbook-grounded instead of list-driven. A
corpus is a folder of JSON files, one per textbook volume, produced by
`textbook_ingest` from the official KTBS PDFs:

    {
      "version": 1,
      "subject": "Science", "grade": 8, "part": "1", "medium": "English",
      "source_file": "science_8.pdf", "sha256": "...",
      "chapters": [
        {"number": 1, "title": "Crop Production and Management",
         "pages": [7, 22],
         "passages": [{"id": "science-8-c01-p001", "section": "1.1 ...",
                       "text": "..."}]}
      ]
    }

Nothing about chapters, grades or topics is hardcoded: the chapter list for a
(subject, grade) IS whatever the ingested textbook contains, and the passages
are the text questions get written from. Several volumes of one subject/grade
(Maths Part 1 + Part 2) are merged in `part` order.

Coverage: `select_passages` walks a chapter's passages with a stride coprime to
their count, so a batch is spread across the whole chapter and successive
batches (via `offset`) visit every passage before any repeats.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import gcd
from pathlib import Path
from typing import Iterable, Optional

from .schemas import Subject
from .syllabus import _normalize_chapter

CORPUS_VERSION = 1
INTRO_SECTION = "Introduction"


@dataclass(frozen=True)
class Passage:
    id: str
    section: str
    text: str


@dataclass(frozen=True)
class TextbookChapter:
    number: int
    title: str
    passages: tuple[Passage, ...]
    part: str = ""


def _part_key(part: str) -> tuple[int, str]:
    m = re.search(r"\d+", part or "")
    return (int(m.group()) if m else 0, part or "")


class TextbookCorpus:
    def __init__(self) -> None:
        # (subject, grade) -> ordered chapters
        self._chapters: dict[tuple[Subject, int], list[TextbookChapter]] = {}

    # --- construction ---

    def add_volume(self, data: dict) -> None:
        if data.get("version") != CORPUS_VERSION:
            raise ValueError(
                f"unsupported textbook corpus version {data.get('version')!r}"
            )
        subject = Subject(data["subject"])
        grade = int(data["grade"])
        part = str(data.get("part") or "")
        chapters: list[TextbookChapter] = []
        for ch in data.get("chapters", []):
            passages = tuple(
                Passage(id=p["id"], section=p.get("section") or INTRO_SECTION, text=p["text"])
                for p in ch.get("passages", [])
                if p.get("text", "").strip()
            )
            chapters.append(
                TextbookChapter(
                    number=int(ch.get("number", 0)),
                    title=str(ch["title"]).strip(),
                    passages=passages,
                    part=part,
                )
            )
        bucket = self._chapters.setdefault((subject, grade), [])
        bucket.extend(chapters)
        # parts in order; chapters within a part in textbook order
        bucket.sort(key=lambda c: (_part_key(c.part), c.number))

    @classmethod
    def from_dir(cls, path: str | Path) -> "TextbookCorpus":
        corpus = cls()
        root = Path(path)
        if not root.is_dir():
            return corpus
        for f in sorted(root.glob("*.json")):
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "chapters" not in data:
                continue  # not a corpus file (e.g. a manifest)
            corpus.add_volume(data)
        return corpus

    # --- lookup ---

    def is_empty(self) -> bool:
        return not self._chapters

    def subjects(self) -> list[Subject]:
        return sorted({s for s, _ in self._chapters}, key=lambda s: s.value)

    def grades(self, subject: Subject) -> list[int]:
        return sorted(g for s, g in self._chapters if s == subject)

    def has_grade(self, subject: Subject, grade: int) -> bool:
        return (subject, int(grade)) in self._chapters

    def chapters(self, subject: Subject, grade: int) -> list[TextbookChapter]:
        return list(self._chapters.get((subject, int(grade)), []))

    def find_chapter(
        self, subject: Subject, grade: int, chapter: str
    ) -> Optional[TextbookChapter]:
        key = _normalize_chapter(chapter)
        for ch in self._chapters.get((subject, int(grade)), []):
            if _normalize_chapter(ch.title) == key:
                return ch
        return None

    def passages(
        self,
        subject: Subject,
        grade: int,
        chapter: str,
        topic: Optional[str] = None,
    ) -> list[Passage]:
        """
        All passages of the chapter in textbook order. With `topic`, only the
        passages whose section title or text mention it; if none do, the whole
        chapter (a topic hint must never leave a request with nothing to
        write from).
        """
        ch = self.find_chapter(subject, grade, chapter)
        if ch is None:
            return []
        passages = list(ch.passages)
        if topic and topic.strip():
            needle = topic.strip().lower()
            narrowed = [
                p for p in passages if needle in p.section.lower() or needle in p.text.lower()
            ]
            if narrowed:
                return narrowed
        return passages

    def section_titles(self, subject: Subject, grade: int, chapter: str) -> list[str]:
        ch = self.find_chapter(subject, grade, chapter)
        if ch is None:
            return []
        seen: list[str] = []
        for p in ch.passages:
            if p.section != INTRO_SECTION and p.section not in seen:
                seen.append(p.section)
        return seen

    def to_syllabus_dict(self, base: Optional[dict] = None) -> dict:
        """
        Syllabus JSON (SyllabusIndex shape) derived from the textbooks. Without
        `base` the result contains ONLY what has been ingested. With `base`,
        subjects/grades the corpus covers are replaced by the textbook's own
        chapter list; everything else in `base` is kept as-is.
        """
        out: dict = {k: dict(v) if isinstance(v, dict) else v for k, v in (base or {}).items()}
        for subject in self.subjects():
            entry = dict(out.get(subject.value) or {})
            grades = {str(g): list(v) for g, v in (entry.get("grades") or {}).items()}
            topics = {k: list(v) for k, v in (entry.get("topics") or {}).items()}
            for grade in self.grades(subject):
                chapters = self.chapters(subject, grade)
                grades[str(grade)] = [c.title for c in chapters]
                for c in chapters:
                    sections = self.section_titles(subject, grade, c.title)
                    if sections:
                        topics[c.title] = sections
            entry["grades"] = dict(sorted(grades.items(), key=lambda kv: int(kv[0])))
            flat: list[str] = []
            seen: set[str] = set()
            for g in sorted(grades, key=int):
                for title in grades[g]:
                    k = _normalize_chapter(title)
                    if k not in seen:
                        seen.add(k)
                        flat.append(title)
            entry["chapters"] = flat
            if topics:
                entry["topics"] = topics
            out[subject.value] = entry
        return out


# ---------------------------------------------------------------------------
# Coverage planning
# ---------------------------------------------------------------------------

def _coprime_stride(n: int) -> int:
    if n < 3:
        return 1
    s = max(1, round(n * 0.6180339887))
    while s < n and gcd(s, n) != 1:
        s += 1
    return s if s < n else 1


def select_passages(
    passages: list[Passage], count: int, offset: int = 0
) -> list[Passage]:
    """
    Pick `count` passages for one batch. Positions `offset .. offset+count-1`
    of a coprime-stride permutation of the chapter: a batch is spread over the
    chapter rather than clustered, and n consecutive positions (across
    successive batches) visit every passage exactly once. If count > n the
    walk wraps and passages repeat.
    """
    n = len(passages)
    if n == 0 or count <= 0:
        return []
    stride = _coprime_stride(n)
    return [passages[((offset + i) * stride) % n] for i in range(count)]
