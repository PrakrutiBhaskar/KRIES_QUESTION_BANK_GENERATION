"""
GenerationEngine — the Module A entry point.

Orchestrates: request validation -> prompt building -> Groq call -> schema
validation -> duplicate check -> marks-format check -> retry-to-fill on
failures -> a clean batch of exactly `request.count` validated Questions.

This is what Module B's `POST /generate` handler calls.

Note the return shape: `generate()` returns a `(questions, report)` tuple.
The report is diagnostic only — Module B should return the questions and log
the report. See exceptions.py for the full FastAPI wiring example.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from .config import settings
from .difficulty import flag_difficulty_mismatch
from .exceptions import GenerationValidationError, GroqAPIError, InvalidRequestError
from .groq_client import GroqClient
from .prompts import build_prompt
from .schemas import GenerationRequest, Question
from .syllabus import SyllabusIndex
from .validation import (
    build_question,
    check_answer_relevance,
    check_marks_format,
    find_duplicates,
    validate_request_combination,
)

logger = logging.getLogger("generation_engine")


@dataclass
class GenerationReport:
    """Returned alongside the questions so callers/tests can inspect what happened."""

    requested_count: int
    returned_count: int
    attempts: int
    dropped_schema_invalid: int = 0
    dropped_marks_format_invalid: int = 0
    dropped_duplicates: int = 0
    dropped_irrelevant: int = 0
    difficulty_warnings: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "requested_count": self.requested_count,
            "returned_count": self.returned_count,
            "attempts": self.attempts,
            "dropped_schema_invalid": self.dropped_schema_invalid,
            "dropped_marks_format_invalid": self.dropped_marks_format_invalid,
            "dropped_duplicates": self.dropped_duplicates,
            "dropped_irrelevant": self.dropped_irrelevant,
            "difficulty_warnings": list(self.difficulty_warnings),
            "rejection_reasons": list(self.rejection_reasons),
        }


class GenerationEngine:
    def __init__(
        self,
        groq_client: GroqClient | None = None,
        syllabus: Optional[SyllabusIndex] = None,
    ):
        self.groq_client = groq_client or GroqClient()
        self.syllabus = syllabus

    async def generate(
        self, request: GenerationRequest
    ) -> tuple[list[Question], GenerationReport]:
        """
        Returns (questions, report). Raises:
          - InvalidRequestError (400) for a bad subject/chapter/type/marks/count combo
          - GroqAPIError (502), bubbled up unchanged from GroqClient
          - GenerationValidationError (422) if a valid batch of `count`
            questions can't be assembled within the retry budget
        """
        problems = validate_request_combination(request, syllabus=self.syllabus)
        if problems:
            raise InvalidRequestError("; ".join(problems))

        accepted: list[Question] = []
        report = GenerationReport(
            requested_count=request.count, returned_count=0, attempts=0
        )

        remaining = request.count
        max_attempts = settings.max_regeneration_retries + 1
        feedback: list[str] = []

        for attempt in range(1, max_attempts + 1):
            if remaining <= 0:
                break
            # counted here, not before the break, so `attempts` reflects the
            # number of Groq calls actually made
            report.attempts = attempt

            batch_request = request.model_copy(update={"count": remaining})
            raw_items = await self._call_groq(batch_request, feedback)

            # Reasons collected this round, fed back into the next prompt so
            # the model corrects course rather than resampling blindly.
            feedback = []

            candidates: list[Question] = []
            for raw in raw_items:
                result = build_question(raw, request)
                if result.error:
                    report.dropped_schema_invalid += 1
                    reason = self._summarize(result.error)
                    feedback.append(f"schema invalid: {reason}")
                    report.rejection_reasons.append(f"schema invalid: {reason}")
                    logger.warning("Schema validation failed, dropping item: %s", reason)
                    continue
                candidates.append(result.question)

            # marks-vs-answer-length + relevance checks
            surviving: list[Question] = []
            for q in candidates:
                format_problems = check_marks_format(q)
                relevance_problems = check_answer_relevance(q)
                if format_problems or relevance_problems:
                    if format_problems:
                        report.dropped_marks_format_invalid += 1
                    else:
                        report.dropped_irrelevant += 1
                    joined = "; ".join(format_problems + relevance_problems)
                    feedback.append(joined)
                    report.rejection_reasons.append(joined)
                    logger.warning(
                        "Format/relevance check failed, dropping item %r: %s",
                        q.text[:60],
                        joined,
                    )
                    continue
                surviving.append(q)

            # duplicate check, against everything accepted so far too
            combined = accepted + surviving
            dup_indices = find_duplicates(combined)
            new_dup_indices = {
                i - len(accepted) for i in dup_indices if i >= len(accepted)
            }
            if new_dup_indices:
                report.dropped_duplicates += len(new_dup_indices)
                feedback.append(
                    f"{len(new_dup_indices)} question(s) duplicated an earlier "
                    f"question — every question must be distinct"
                )
            surviving = [
                q for i, q in enumerate(surviving) if i not in new_dup_indices
            ]

            # optional second-pass semantic check
            if settings.enable_llm_relevance_check and surviving:
                surviving = await self._filter_by_llm_relevance(surviving, report)

            for q in surviving:
                warning = flag_difficulty_mismatch(q)
                if warning:
                    report.difficulty_warnings.append(f"{q.id}: {warning}")

            accepted.extend(surviving[:remaining])
            remaining = request.count - len(accepted)

        report.returned_count = len(accepted)

        if len(accepted) < request.count:
            raise GenerationValidationError(
                f"Only produced {len(accepted)}/{request.count} valid questions "
                f"after {report.attempts} attempt(s). "
                f"Dropped: {report.dropped_schema_invalid} schema-invalid, "
                f"{report.dropped_marks_format_invalid} marks-format-invalid, "
                f"{report.dropped_irrelevant} irrelevant, "
                f"{report.dropped_duplicates} duplicates.",
                context={"report": report.as_dict()},
            )

        return accepted, report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _call_groq(
        self, request: GenerationRequest, feedback: list[str] | None = None
    ) -> list[dict]:
        system_prompt, user_prompt = build_prompt(request, retry_feedback=feedback)
        return await self.groq_client.complete_json(system_prompt, user_prompt)

    @staticmethod
    def _summarize(error: str, limit: int = 200) -> str:
        collapsed = " ".join(error.split())
        return collapsed[:limit]

    async def verify_relevance_llm(self, questions: list[Question]) -> list[bool]:
        """
        Optional second LLM pass: asks the model whether each answer actually
        answers its question. Returns one boolean per input question, in
        order.

        This is the semantic counterpart to validation.check_answer_relevance,
        which only catches structurally broken answers (empty, echoed
        question text). It costs one extra Groq call per batch, so it's off
        unless ENABLE_LLM_RELEVANCE_CHECK is set. It does NOT replace the
        manual factual spot-check in test-plan.md Section 4 — the model is
        checking coherence, not truth.

        Fails open: if the check itself errors, every question is treated as
        relevant rather than discarding a whole batch over a flaky call.
        """
        if not questions:
            return []

        items = [
            {"index": i, "question": q.text, "answer": q.answer}
            for i, q in enumerate(questions)
        ]
        system_prompt = (
            "You check whether an answer actually answers the question asked. "
            "You reply with JSON only."
        )
        user_prompt = (
            "For each item below, decide whether the answer is a coherent, "
            "on-topic response to its question. Ignore style and length; judge "
            "only whether the answer addresses the question.\n\n"
            f"{json.dumps(items, ensure_ascii=False)}\n\n"
            'Return ONLY a JSON array like [{"index": 0, "relevant": true}, ...] '
            "with one entry per item, no commentary."
        )

        try:
            raw = await self.groq_client.complete_json(system_prompt, user_prompt)
        except GroqAPIError as e:
            logger.warning("LLM relevance check failed, skipping: %s", e)
            return [True] * len(questions)

        verdicts = [True] * len(questions)
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            if isinstance(idx, int) and 0 <= idx < len(questions):
                verdicts[idx] = bool(entry.get("relevant", True))
        return verdicts

    async def _filter_by_llm_relevance(
        self, questions: list[Question], report: GenerationReport
    ) -> list[Question]:
        verdicts = await self.verify_relevance_llm(questions)
        kept: list[Question] = []
        for q, relevant in zip(questions, verdicts):
            if relevant:
                kept.append(q)
            else:
                report.dropped_irrelevant += 1
                reason = "LLM relevance check: answer does not address the question"
                report.rejection_reasons.append(reason)
                logger.warning("%s: %r", reason, q.text[:60])
        return kept
