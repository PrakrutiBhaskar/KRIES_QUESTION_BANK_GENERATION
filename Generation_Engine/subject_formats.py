"""
Marks-to-format mapping, configurable per subject.

spec.md Module A: "Marks-to-format mapping configurable per subject (Math
needs step derivations; Social Science needs distinct points)."

Both the prompt layer and the validation layer read from this one registry,
so a subject's rules can't drift between "what we asked the model for" and
"what we check the model returned". Previously these lived as two separate
hardcoded dicts — one in prompts.py, one in validation.py — which is exactly
how a prompt and its validator end up disagreeing.

To add or tune a subject, edit `SUBJECT_FORMATS` (or call
`register_subject_format` at startup from the Backend).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .schemas import Subject


@dataclass(frozen=True)
class MarksRule:
    """
    Expected answer shape for one (subject, marks) combination.

    min_points / max_points bound the number of distinct points or steps the
    answer should contain; min_words / max_words bound its length. `None`
    means "unbounded in that direction".
    """

    min_points: Optional[int] = None
    max_points: Optional[int] = None
    min_words: Optional[int] = None
    max_words: Optional[int] = None
    forbid_explanation: bool = False
    # Regex the answer must match, plus the message shown when it doesn't.
    required_pattern: Optional[str] = None
    required_pattern_message: str = ""


@dataclass(frozen=True)
class SubjectFormat:
    """Everything subject-specific the engine needs, in one place."""

    # Guidance injected into every prompt for this subject.
    prompt_note: str
    # marks -> rule overrides. Anything absent falls back to DEFAULT_MARKS_RULES.
    marks_rules: dict[int, MarksRule] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Baseline rules, applied to every subject unless overridden below.
# Derived from the mark-scheme reference table in spec.md Section 7.
# ---------------------------------------------------------------------------

DEFAULT_MARKS_RULES: dict[int, MarksRule] = {
    # Single word/phrase or one-line fact, no explanation.
    1: MarksRule(max_points=1, max_words=15, forbid_explanation=True),
    # 1-2 lines with one supporting reason/point.
    2: MarksRule(min_points=1, max_points=2, min_words=3, max_words=60),
    # Exactly 3 distinct points or steps.
    3: MarksRule(min_points=3, max_points=3),
    # Detailed multi-point/step answer, exam-response style.
    5: MarksRule(min_points=3, min_words=40),
}


# ---------------------------------------------------------------------------
# Per-subject configuration
# ---------------------------------------------------------------------------

SUBJECT_FORMATS: dict[Subject, SubjectFormat] = {
    Subject.MATH: SubjectFormat(
        prompt_note=(
            "For 5-mark answers, show the FULL step-by-step derivation, not "
            "just the final answer — number each step. For lower marks, show "
            "only as much working as the mark value implies (1 mark = no "
            "working, 2 marks = 1 line of working, 3 marks = 2-3 steps)."
        ),
        marks_rules={
            5: MarksRule(
                min_points=3,
                min_words=40,
                required_pattern=r"step|derive|substitut|therefore|hence|=",
                required_pattern_message=(
                    "Math 5-mark answers should show step-by-step derivation "
                    "language or working"
                ),
            ),
        },
    ),
    Subject.SOCIAL_SCIENCE: SubjectFormat(
        prompt_note=(
            "For 5-mark answers, split the answer into clearly labeled "
            "sections (e.g. 'Causes:' and 'Effects:', or 'Causes:' / "
            "'Consequences:' as appropriate to the question) rather than one "
            "undivided paragraph."
        ),
        marks_rules={
            5: MarksRule(
                min_points=3,
                min_words=40,
                required_pattern=r"cause|effect|reason|consequence|impact|result",
                required_pattern_message=(
                    "Social Science 5-mark answers should reference "
                    "causes/effects language"
                ),
            ),
        },
    ),
    Subject.SCIENCE: SubjectFormat(
        prompt_note=(
            "Where relevant, reference a diagram or concrete example in the "
            "explanation text (e.g. 'as shown in a labeled diagram of ...'), "
            "even though no actual image is generated."
        ),
    ),
    Subject.ENGLISH: SubjectFormat(
        prompt_note=(
            "Questions must be self-contained: if the question is passage- or "
            "grammar-based, include the short passage or sentence needed to "
            "answer it directly in the question text rather than assuming an "
            "external passage the student cannot see. Quote the exact words "
            "the question asks about."
        ),
    ),
    Subject.KANNADA: SubjectFormat(
        prompt_note=(
            "Write the question text, options and answer in Kannada script. "
            "Questions must be self-contained: if the question is passage- or "
            "grammar-based, include the short passage or sentence needed to "
            "answer it directly in the question text rather than assuming an "
            "external passage the student cannot see."
        ),
        marks_rules={
            # Kannada script has no whitespace-delimited word count that maps
            # cleanly onto the English-tuned bounds, so length limits are
            # loosened and point structure carries the check instead.
            1: MarksRule(max_points=1, max_words=20, forbid_explanation=True),
            2: MarksRule(min_points=1, max_points=2, min_words=2, max_words=80),
            5: MarksRule(min_points=3, min_words=25),
        },
    ),
}


def get_subject_format(subject: Subject) -> SubjectFormat:
    return SUBJECT_FORMATS.get(subject, SubjectFormat(prompt_note=""))


def get_marks_rule(subject: Subject, marks: int) -> MarksRule:
    """Subject-specific rule if one exists, else the baseline rule."""
    fmt = get_subject_format(subject)
    if marks in fmt.marks_rules:
        return fmt.marks_rules[marks]
    return DEFAULT_MARKS_RULES.get(marks, MarksRule())


def get_prompt_note(subject: Subject) -> str:
    return get_subject_format(subject).prompt_note


def register_subject_format(subject: Subject, fmt: SubjectFormat) -> None:
    """
    Override a subject's configuration at runtime. Lets the Backend tune
    subject rules from its own config without editing this module.
    """
    SUBJECT_FORMATS[subject] = fmt


def compile_required_pattern(rule: MarksRule):
    if not rule.required_pattern:
        return None
    return re.compile(rule.required_pattern, re.IGNORECASE)
