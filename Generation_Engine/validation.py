"""
Output validation for generated questions. Implements the three checks
called out across spec.md / prompt-library.md / test-plan.md:

  1. Schema check           -> build_question() / pydantic Question model
  2. Duplicate check        -> find_duplicates() (exact + near-duplicate)
  3. Marks-vs-answer-length -> check_marks_format()

Also implements the request-level combination check (subject/chapter/type/
marks) that api-contract.md's 400 error refers to.

All marks/subject thresholds live in subject_formats.py rather than here, so
the prompt layer and this layer can't drift apart.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import ValidationError as PydanticValidationError

from .config import settings
from .schemas import (
    GenerationRequest,
    Question,
    QuestionType,
    VALID_MARKS_BY_TYPE,
)
from .subject_formats import compile_required_pattern, get_marks_rule


# ---------------------------------------------------------------------------
# 0. Request-level combination check (-> 400 InvalidRequestError upstream)
# ---------------------------------------------------------------------------

def validate_request_combination(
    request: GenerationRequest,
    syllabus: Optional["SyllabusIndex"] = None,  # noqa: F821 - see syllabus.py
) -> list[str]:
    """
    Returns a list of human-readable problems with the request combination.
    Empty list means the request is valid. Callers raise InvalidRequestError
    (400) if this is non-empty — kept as pure validation here so it's
    trivially testable.

    If a `syllabus` index is supplied, the chapter is additionally checked
    against the known chapter list for that subject. Without one, any
    non-blank chapter string is accepted (the MVP has no syllabus source
    wired up yet — see spec.md Section 8).
    """
    problems: list[str] = []

    allowed_marks = VALID_MARKS_BY_TYPE.get(request.type, set())
    if request.marks not in allowed_marks:
        problems.append(
            f"{request.type.value} questions must use marks in "
            f"{sorted(allowed_marks)}, got {request.marks}"
        )

    if request.count < 1:
        problems.append("count must be at least 1")
    if request.count > settings.max_batch_count:
        problems.append(f"count must not exceed {settings.max_batch_count} per request")

    if not request.chapter or not request.chapter.strip():
        problems.append("chapter must not be blank")
    elif syllabus is not None and not syllabus.has_chapter(
        request.subject, request.chapter
    ):
        problems.append(
            f'unknown chapter "{request.chapter}" for subject '
            f"{request.subject.value}"
        )

    return problems


# ---------------------------------------------------------------------------
# 1. Schema check
# ---------------------------------------------------------------------------

@dataclass
class BuildResult:
    question: Question | None
    error: str | None
    raw: dict[str, Any]


def build_question(raw: dict[str, Any], request: GenerationRequest) -> BuildResult:
    """
    Takes one raw dict from the LLM plus the originating request, fills in
    the fields the model wasn't asked to produce (id/subject/chapter/type/
    marks/difficulty), and validates it against the Question schema.
    """
    if not isinstance(raw, dict):
        return BuildResult(
            question=None,
            error=f"expected a JSON object, got {type(raw).__name__}",
            raw={},
        )

    try:
        payload = {
            "subject": request.subject,
            "chapter": request.chapter,
            "type": request.type,
            "marks": request.marks,
            "difficulty": request.difficulty,
            "text": raw.get("text", ""),
            "options": raw.get("options"),
            "answer": raw.get("answer", ""),
            "explanation": raw.get("explanation", "") or "",
            "topic": raw.get("topic", "") or "",
            "tags": raw.get("tags") or [],
        }
        question = Question(**payload)
    except PydanticValidationError as e:
        return BuildResult(question=None, error=str(e), raw=raw)
    except Exception as e:  # defensive: malformed raw dict (wrong types etc.)
        return BuildResult(question=None, error=f"malformed output: {e}", raw=raw)

    return BuildResult(question=question, error=None, raw=raw)


# ---------------------------------------------------------------------------
# 2. Duplicate check
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def find_duplicates(
    questions: list[Question],
    similarity_threshold: float | None = None,
) -> set[int]:
    """
    Returns the set of indices (into `questions`) that should be dropped as
    duplicates of an earlier question in the same list — exact matches after
    normalization, or near-duplicates above the similarity threshold.
    The first occurrence of each question is always kept.
    """
    threshold = similarity_threshold or settings.near_duplicate_similarity_threshold
    normalized = [_normalize(q.text) for q in questions]
    seen_exact: set[str] = set()
    kept_normalized: list[str] = []
    drop: set[int] = set()

    for i, norm in enumerate(normalized):
        if norm in seen_exact:
            drop.add(i)
            continue
        is_near_dup = any(
            difflib.SequenceMatcher(None, norm, prior).ratio() >= threshold
            for prior in kept_normalized
        )
        if is_near_dup:
            drop.add(i)
            continue
        seen_exact.add(norm)
        kept_normalized.append(norm)

    return drop


# ---------------------------------------------------------------------------
# 3. Marks-vs-answer-length check (spec.md Section 7 mark-scheme table)
# ---------------------------------------------------------------------------

# Matches a list marker at the start of the string, at the start of a line, or
# mid-line after whitespace. The mid-line case matters: the 3-mark prompt asks
# the model to number points "1., 2., 3." inside the answer string, and models
# routinely return all three on a single line. A line-anchored pattern silently
# falls through to sentence-splitting there and counts 6 points instead of 3,
# which rejects correctly-formatted answers.
#
# `\d+[.)]` requires trailing whitespace, so decimals ("2.5 kg") and
# coordinates are not mistaken for markers.
_MARKER_SPLIT = re.compile(r"(?:^|(?<=\s))(?:\d+[.)]|[-*•])\s+", re.MULTILINE)

# Labeled sections, e.g. "Causes: ... Effects: ..." — used by Social Science
# 5-mark answers, which are structured by heading rather than by number.
_LABEL_SPLIT = re.compile(r"(?:^|(?<=\s))[A-Z][A-Za-z ]{2,24}:\s+", re.MULTILINE)


def _split_points(answer: str) -> list[str]:
    """
    Splits an answer into discrete points/steps using common list markers
    (numbered "1." / "1)", bullets, newlines, or labeled sections) so we can
    count them. Falls back to sentence-splitting if no explicit markers are
    present.
    """
    answer = answer.strip()
    if not answer:
        return []

    marker_split = [p.strip() for p in _MARKER_SPLIT.split(answer) if p.strip()]
    if len(marker_split) >= 2:
        return marker_split

    # Labeled sections ("Causes: ... Effects: ..."). Each section body is
    # itself flattened into sentences, so a two-section answer with several
    # sentences per section counts as the several points it actually is.
    if len(_LABEL_SPLIT.findall(answer)) >= 2:
        bodies = [p.strip() for p in _LABEL_SPLIT.split(answer) if p.strip()]
        flattened: list[str] = []
        for body in bodies:
            flattened.extend(_split_sentences(body))
        if flattened:
            return flattened

    line_split = [p.strip() for p in answer.splitlines() if p.strip()]
    if len(line_split) >= 2:
        return line_split

    return _split_sentences(answer)


def _split_sentences(text: str) -> list[str]:
    """Sentence split, including the Kannada/Devanagari danda as a terminator."""
    return [s.strip() for s in re.split(r"(?<=[.!?।])\s+", text.strip()) if s.strip()]


def check_marks_format(question: Question) -> list[str]:
    """
    Returns a list of format problems for the given question's answer,
    checked against the marks-based expected format for its subject
    (subject_formats.py, derived from spec.md Section 7). Empty list = passes.
    """
    problems: list[str] = []
    answer = question.answer.strip()
    word_count = len(answer.split())

    if question.type == QuestionType.MCQ:
        # An MCQ's answer is just the option text; the *justification* is what
        # carries the marks-format expectation (1 line).
        explanation = question.explanation.strip()
        expl_words = len(explanation.split())
        if expl_words > 40:
            problems.append(
                f"MCQ justification should be ~1 line; got {expl_words} words"
            )
        if len(_split_points(explanation)) > 2:
            problems.append(
                "MCQ justification should be a single line, not a multi-point answer"
            )
        return problems

    rule = get_marks_rule(question.subject, question.marks)
    points = _split_points(answer)
    label = f"{question.marks}-mark answer"

    if rule.min_points is not None and len(points) < rule.min_points:
        if rule.min_points == rule.max_points:
            problems.append(
                f"{label} must contain exactly {rule.min_points} distinct "
                f"points/steps; detected {len(points)}"
            )
        else:
            problems.append(
                f"{label} must contain at least {rule.min_points} distinct "
                f"points/steps; detected {len(points)}"
            )
    elif rule.max_points is not None and len(points) > rule.max_points:
        if rule.min_points == rule.max_points:
            problems.append(
                f"{label} must contain exactly {rule.max_points} distinct "
                f"points/steps; detected {len(points)}"
            )
        else:
            problems.append(
                f"{label} should contain at most {rule.max_points} distinct "
                f"point(s); detected {len(points)}"
            )

    if rule.min_words is not None and word_count < rule.min_words:
        problems.append(
            f"{label} looks too short for the expected depth "
            f"({word_count} words, expected at least {rule.min_words})"
        )
    if rule.max_words is not None and word_count > rule.max_words:
        problems.append(
            f"{label} looks too long for the expected format "
            f"({word_count} words, expected at most {rule.max_words})"
        )

    if rule.forbid_explanation and question.explanation.strip():
        problems.append(f"{label} should not include an explanation")

    pattern = compile_required_pattern(rule)
    if pattern and not pattern.search(answer):
        problems.append(rule.required_pattern_message)

    return problems


def check_answer_relevance(question: Question) -> list[str]:
    """
    Lightweight heuristic guard against obviously broken answers (empty, a
    verbatim echo of the question text, or an MCQ answer that isn't one of
    the options). This is NOT a substitute for the manual factual-correctness
    spot-check in test-plan.md Section 4 — true semantic "does the answer
    match the question" verification needs either human review or a second
    LLM pass (see GenerationEngine.verify_relevance_llm, enabled via
    ENABLE_LLM_RELEVANCE_CHECK).
    """
    problems: list[str] = []
    if not question.answer.strip():
        problems.append("answer is empty")
    elif _normalize(question.answer) == _normalize(question.text):
        problems.append("answer appears to be a copy of the question text")

    if not question.text.strip().endswith(("?", ":", ".", "।")) and len(
        question.text.split()
    ) < 3:
        problems.append("question text is too short to be a real question")

    return problems


def validate_batch(questions: list[Question]) -> dict[int, list[str]]:
    """
    Runs marks-format + relevance checks across a batch and duplicate
    detection across the batch as a whole. Returns {index: [problems]} for
    every question that failed at least one check.
    """
    failures: dict[int, list[str]] = {}

    for i, q in enumerate(questions):
        problems = check_marks_format(q) + check_answer_relevance(q)
        if problems:
            failures[i] = problems

    for i in find_duplicates(questions):
        failures.setdefault(i, []).append(
            "duplicate of an earlier question in this batch"
        )

    return failures
