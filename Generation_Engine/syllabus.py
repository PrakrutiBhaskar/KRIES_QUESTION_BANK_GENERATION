"""
Syllabus index — Subject -> Chapter lookup.

spec.md Module A: syllabus data is structured as Subject -> Chapter, with
`topic` captured as a tag on each generated question rather than a separate
hierarchy level.

The *source* of that data is still an open decision (spec.md Section 8: which
PDF-parsing tool, how much manual cleanup). This module deliberately doesn't
pick one. It defines the shape the parsed output must land in and the lookup
the engine needs, so the PDF pipeline can be dropped in behind
`SyllabusIndex.from_json` without touching the engine.

Expected JSON shape:

    {
      "Science": {
        "grade": 8,
        "chapters": ["Nutrition in Plants", "Force and Pressure"]
      },
      "Math": {"chapters": ["Rational Numbers", "Linear Equations"]}
    }

Note: the "grade" key above is unrelated to `GenerationRequest.grade` /
`Question.grade` (schemas.py) — it's syllabus-source metadata (which grade
this subject's chapter list was parsed for) and isn't currently read by
`from_dict`. A generation request's grade is chosen by the caller per call,
independent of whatever grade the syllabus chapter list itself came from.

The index is optional everywhere. With no index supplied, any non-blank
chapter string is accepted — which is the MVP behaviour, since no syllabus
data has been ingested yet.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Mapping

from .schemas import Subject


def _normalize_chapter(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"^(chapter|ch\.?|adhyaya)\s*\d+\s*[:.\-]?\s*", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


class SyllabusIndex:
    """Case- and punctuation-insensitive Subject -> Chapter lookup."""

    def __init__(self, chapters_by_subject: Mapping[Subject, Iterable[str]]):
        self._chapters: dict[Subject, dict[str, str]] = {}
        for subject, chapters in chapters_by_subject.items():
            self._chapters[subject] = {
                _normalize_chapter(c): c.strip() for c in chapters if c and c.strip()
            }

    # --- construction ---

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "SyllabusIndex":
        chapters_by_subject: dict[Subject, list[str]] = {}
        for subject_name, entry in data.items():
            try:
                subject = Subject(subject_name)
            except ValueError:
                raise ValueError(f"unknown subject in syllabus data: {subject_name!r}")
            if isinstance(entry, dict):
                chapters = entry.get("chapters", [])
            else:
                chapters = entry  # allow a bare list of chapter names
            if not isinstance(chapters, list):
                raise ValueError(f"chapters for {subject_name} must be a list")
            chapters_by_subject[subject] = [str(c) for c in chapters]
        return cls(chapters_by_subject)

    @classmethod
    def from_json(cls, path: str | Path) -> "SyllabusIndex":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    # --- lookup ---

    def subjects(self) -> list[Subject]:
        return list(self._chapters.keys())

    def chapters(self, subject: Subject) -> list[str]:
        """Chapter names as originally written, in insertion order."""
        return list(self._chapters.get(subject, {}).values())

    def has_chapter(self, subject: Subject, chapter: str) -> bool:
        return _normalize_chapter(chapter) in self._chapters.get(subject, {})

    def canonical_chapter(self, subject: Subject, chapter: str) -> str | None:
        """Returns the chapter name as the syllabus spells it, or None."""
        return self._chapters.get(subject, {}).get(_normalize_chapter(chapter))

    def __len__(self) -> int:
        return sum(len(c) for c in self._chapters.values())
