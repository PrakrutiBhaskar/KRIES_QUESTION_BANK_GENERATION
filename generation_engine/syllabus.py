"""
Syllabus index — Subject -> (Grade ->) Chapter lookup.

Scope: the Karnataka State Board (KSEEB) syllabus, as taught from the
Karnataka Textbook Society (KTBS) textbooks, for grades 7-9. The index is what
makes generation *strictly* syllabus-bound: a request is rejected (400) unless
its chapter is part of the requested grade's syllabus for that subject, and
the chapter's sub-topics (when the data has them) are fed into the prompt as
the allowed scope.

Expected JSON shape (per subject):

    {
      "Science": {
        "chapters": ["Nutrition in Plants", "Force and Pressure"],   # union
        "grades": {                                                  # optional
          "7": ["Nutrition in Plants"],
          "8": ["Force and Pressure"]
        },
        "topics": {                                                  # optional
          "Nutrition in Plants": ["Photosynthesis", "Modes of nutrition"]
        }
      },
      "Math": {"chapters": ["Rational Numbers"]}   # a bare list also works
    }

- `chapters` is every chapter of the subject across grades. If it is omitted,
  it is derived from the `grades` lists.
- `grades` scopes chapters to a grade. When a subject has it, the engine only
  accepts a chapter for the grades that list it. A subject WITHOUT it cannot be
  grade-checked: its chapters are accepted for any grade (see
  `is_grade_scoped`). Filling in `grades` for every subject is what makes the
  restriction complete.
- `topics` maps a chapter to its sub-topics. They are injected into the prompt
  so the model stays inside the chapter. Optional.
- Top-level keys that start with "_" (e.g. "_meta") are metadata and ignored.

The "grade" key some older data files carry at subject level is unrelated to
`GenerationRequest.grade` and is ignored here.

The index is optional in the engine: with no index supplied, any non-blank
chapter string is accepted unless `REQUIRE_SYLLABUS` is enabled
(see `validation.validate_request_combination`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Mapping, Optional

from .schemas import Subject


def _normalize_chapter(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"^(chapter|ch\.?|adhyaya)\s*\d+\s*[:.\-]?\s*", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


class SyllabusIndex:
    """Case- and punctuation-insensitive Subject -> (Grade ->) Chapter lookup."""

    def __init__(
        self,
        chapters_by_subject: Mapping[Subject, Iterable[str]],
        chapters_by_grade: Optional[Mapping[Subject, Mapping[int, Iterable[str]]]] = None,
        topics_by_chapter: Optional[Mapping[Subject, Mapping[str, Iterable[str]]]] = None,
    ):
        # subject -> normalised name -> display name (insertion-ordered)
        self._chapters: dict[Subject, dict[str, str]] = {}
        for subject, chapters in chapters_by_subject.items():
            self._chapters[subject] = {
                _normalize_chapter(c): c.strip() for c in chapters if c and c.strip()
            }

        # subject -> grade -> set of normalised chapter names
        self._by_grade: dict[Subject, dict[int, list[str]]] = {}
        for subject, grades in (chapters_by_grade or {}).items():
            union = self._chapters.setdefault(subject, {})
            per_grade: dict[int, list[str]] = {}
            for grade, chapters in grades.items():
                keys: list[str] = []
                for c in chapters:
                    if not c or not str(c).strip():
                        continue
                    key = _normalize_chapter(str(c))
                    if key not in union:
                        # A grade list may legitimately introduce a chapter the
                        # flat list left out; keep the union complete.
                        union[key] = str(c).strip()
                    keys.append(key)
                per_grade[int(grade)] = keys
            if per_grade:
                self._by_grade[subject] = per_grade

        # subject -> normalised chapter -> topics
        self._topics: dict[Subject, dict[str, list[str]]] = {}
        for subject, by_chapter in (topics_by_chapter or {}).items():
            self._topics[subject] = {
                _normalize_chapter(ch): [str(t).strip() for t in ts if str(t).strip()]
                for ch, ts in by_chapter.items()
            }

    # --- construction ---

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "SyllabusIndex":
        chapters_by_subject: dict[Subject, list[str]] = {}
        chapters_by_grade: dict[Subject, dict[int, list[str]]] = {}
        topics: dict[Subject, dict[str, list[str]]] = {}

        for subject_name, entry in data.items():
            if str(subject_name).startswith("_"):  # metadata, e.g. "_meta"
                continue
            try:
                subject = Subject(subject_name)
            except ValueError:
                raise ValueError(f"unknown subject in syllabus data: {subject_name!r}")

            grades_raw: object = None
            topics_raw: object = None
            if isinstance(entry, dict):
                chapters = entry.get("chapters", [])
                grades_raw = entry.get("grades")
                topics_raw = entry.get("topics")
            else:
                chapters = entry  # allow a bare list of chapter names
            if not isinstance(chapters, list):
                raise ValueError(f"chapters for {subject_name} must be a list")

            grade_map: dict[int, list[str]] = {}
            if grades_raw is not None:
                if not isinstance(grades_raw, dict):
                    raise ValueError(f"grades for {subject_name} must be an object")
                for g, names in grades_raw.items():
                    try:
                        grade = int(g)
                    except (TypeError, ValueError):
                        raise ValueError(
                            f"grade key {g!r} for {subject_name} is not an integer"
                        )
                    if not isinstance(names, list):
                        raise ValueError(
                            f"grade {g} chapters for {subject_name} must be a list"
                        )
                    grade_map[grade] = [str(n) for n in names]

            flat = [str(c) for c in chapters]
            if not flat and grade_map:
                # Derive the union from the grade lists, preserving order.
                seen: set[str] = set()
                for g in sorted(grade_map):
                    for n in grade_map[g]:
                        key = _normalize_chapter(n)
                        if key not in seen:
                            seen.add(key)
                            flat.append(n)
            chapters_by_subject[subject] = flat
            if grade_map:
                chapters_by_grade[subject] = grade_map

            if topics_raw is not None:
                if not isinstance(topics_raw, dict):
                    raise ValueError(f"topics for {subject_name} must be an object")
                topic_map: dict[str, list[str]] = {}
                for ch, ts in topics_raw.items():
                    if not isinstance(ts, list):
                        raise ValueError(
                            f"topics for {subject_name} / {ch!r} must be a list"
                        )
                    topic_map[str(ch)] = [str(t) for t in ts]
                topics[subject] = topic_map

        return cls(chapters_by_subject, chapters_by_grade, topics)

    @classmethod
    def from_json(cls, path: str | Path) -> "SyllabusIndex":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    # --- lookup ---

    def subjects(self) -> list[Subject]:
        return list(self._chapters.keys())

    def is_grade_scoped(self, subject: Subject) -> bool:
        """True when the data says which grade each chapter belongs to."""
        return bool(self._by_grade.get(subject))

    def grades(self, subject: Subject) -> list[int]:
        return sorted(self._by_grade.get(subject, {}))

    def chapters(self, subject: Subject, grade: Optional[int] = None) -> list[str]:
        """
        Chapter names as originally written, in insertion order. With `grade`
        set and the subject grade-scoped, only that grade's chapters.
        """
        all_chapters = self._chapters.get(subject, {})
        if grade is not None and self.is_grade_scoped(subject):
            return [
                all_chapters[k]
                for k in self._by_grade[subject].get(int(grade), [])
                if k in all_chapters
            ]
        return list(all_chapters.values())

    def grades_for_chapter(self, subject: Subject, chapter: str) -> list[int]:
        """Grades whose syllabus lists this chapter (empty if not grade-scoped)."""
        key = _normalize_chapter(chapter)
        return sorted(
            g for g, keys in self._by_grade.get(subject, {}).items() if key in keys
        )

    def has_chapter(
        self, subject: Subject, chapter: str, grade: Optional[int] = None
    ) -> bool:
        key = _normalize_chapter(chapter)
        if key not in self._chapters.get(subject, {}):
            return False
        if grade is not None and self.is_grade_scoped(subject):
            return key in self._by_grade[subject].get(int(grade), [])
        return True

    def canonical_chapter(
        self, subject: Subject, chapter: str, grade: Optional[int] = None
    ) -> str | None:
        """Returns the chapter name as the syllabus spells it, or None."""
        if not self.has_chapter(subject, chapter, grade):
            return None
        return self._chapters[subject][_normalize_chapter(chapter)]

    def topics(self, subject: Subject, chapter: str) -> list[str]:
        """Sub-topics the syllabus lists for a chapter (empty if none recorded)."""
        return list(self._topics.get(subject, {}).get(_normalize_chapter(chapter), []))

    def __len__(self) -> int:
        return sum(len(c) for c in self._chapters.values())
