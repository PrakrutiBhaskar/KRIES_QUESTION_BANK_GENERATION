"""
Output validation for generated questions. Implements the three checks
called out across spec.md / prompt-library.md / test-plan.md:

  1. Schema check           -> build_question() / pydantic Question model
  2. Duplicate check        -> find_duplicates() (exact + near-duplicate)
  3. Marks-vs-answer-length -> check_marks_format()

Also implements the request-level combination check (subject/chapter/type/
marks) that api-contract.md's 400 error refers to.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from .config import settings
from .schemas import (
    Difficulty,
    GenerationRequest,
    Question,
    QuestionType,
    Subject,
    VALID_MARKS_BY_TYPE,
)


# ---------------------------------------------------------------------------
# 0. Request-level combination check (-> 400 InvalidRequestError upstream)
# ---------------------------------------------------------------------------

def validate_request_combination(request: GenerationRequest) -> list[str]:
    """
    Returns a list of human-readable problems with the request combination.
    Empty list means the request is valid. Callers raise InvalidRequestError
    (400) if this is non-empty — kept as pure validation here so it's
    trivially testable.
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
            "explanation": raw.get("explanation", ""),
            "topic": raw.get("topic", ""),
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
# 3. Marks-vs-answer-length check (project-context.md mark-scheme table)
# ---------------------------------------------------------------------------

def _split_points(answer: str) -> list[str]:
    """
    Splits an answer into discrete points/steps using common list markers
    (numbered "1." / "1)", bullets, or newlines) so we can count them. Falls
    back to sentence-splitting if no explicit markers are present.
    """
    marker_split = re.split(r"(?:\n|^)\s*(?:\d+[.)]|[-*•])\s+", answer.strip())
    marker_split = [p.strip() for p in marker_split if p.strip()]
    if len(marker_split) >= 2:
        return marker_split

    sentence_split = re.split(r"(?<=[.!?])\s+", answer.strip())
    return [s.strip() for s in sentence_split if s.strip()]


def check_marks_format(question: Question) -> list[str]:
    """
    Returns a list of format problems for the given question's answer,
    checked against the marks-based expected format
    (project-context.md / spec.md Section 7). Empty list = passes.
    """
    problems: list[str] = []
    answer = question.answer.strip()
    word_count = len(answer.split())

    if question.type == QuestionType.MCQ:
        # MCQ answers are the option text; the *justification* is what
        # carries the marks-format expectation (1-line).
        expl_words = len(question.explanation.split())
        if expl_words > 40:
            problems.append(
                f"MCQ justification should be ~1 line; got {expl_words} words"
            )
        return problems

    if question.marks == 1:
        if word_count > 8:
            problems.append(
                f"1-mark answer should be a single word/phrase; got {word_count} words"
            )
        if question.explanation.strip():
            problems.append("1-mark answer should not include an explanation")

    elif question.marks == 2:
        points = _split_points(answer)
        if len(points) > 2:
            problems.append(
                f"2-mark answer should be 1-2 lines with one supporting point; "
                f"detected {len(points)} distinct points"
            )
        if word_count > 60:
            problems.append(
                f"2-mark answer looks too long for a 1-2 line response "
                f"({word_count} words)"
            )
        if word_count < 3:
            problems.append("2-mark answer is too short to contain a supporting point")

    elif question.marks == 3:
        points = _split_points(answer)
        if len(points) != 3:
            problems.append(
                f"3-mark answer must contain exactly 3 distinct points/steps; "
                f"detected {len(points)}"
            )

    elif question.marks == 5:
        points = _split_points(answer)
        if len(points) < 3:
            problems.append(
                f"5-mark answer must be a detailed multi-point response; "
                f"detected only {len(points)} distinct point(s)"
            )
        if word_count < 40:
            problems.append(
                f"5-mark answer looks too short for exam-response depth "
                f"({word_count} words)"
            )

        subject_checks = {
            Subject.MATH: (
                r"step|derive|substitut|therefore|hence",
                "Math 5-mark answers should show step-by-step derivation language",
            ),
            Subject.SOCIAL_SCIENCE: (
                r"cause|effect|reason|consequence|impact|result",
                "Social Science 5-mark answers should reference causes/effects language",
            ),
        }
        check = subject_checks.get(question.subject)
        if check:
            pattern, message = check
            if not re.search(pattern, answer, re.IGNORECASE):
                problems.append(message)

    return problems


def check_answer_relevance(question: Question) -> list[str]:
    """
    Lightweight heuristic guard against obviously broken answers (empty,
    or a verbatim echo of the question text). This is NOT a substitute for
    the manual factual-correctness spot-check in test-plan.md Section 4 —
    true semantic "does the answer match the question" verification needs
    either human review or a second LLM pass (see engine.verify_relevance_llm
    for an optional hook).
    """
    problems: list[str] = []
    if not question.answer.strip():
        problems.append("answer is empty")
    elif _normalize(question.answer) == _normalize(question.text):
        problems.append("answer appears to be a copy of the question text")
    return problems


def validate_batch(
    questions: list[Question],
) -> dict[int, list[str]]:
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
        failures.setdefault(i, []).append("duplicate of an earlier question in this batch")

    return failures
