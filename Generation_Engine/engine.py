"""
GenerationEngine — the Module A entry point.

Orchestrates: request validation -> prompt building -> Groq call -> schema
validation -> duplicate check -> marks-format check -> retry-to-fill on
failures -> a clean batch of exactly `request.count` validated Questions.

This is what Module B's `POST /generate` handler calls directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import settings
from .difficulty import flag_difficulty_mismatch
from .exceptions import GenerationValidationError, InvalidRequestError
from .groq_client import GroqClient
from .prompts import build_prompt
from .schemas import GenerationRequest, Question
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
    difficulty_warnings: list[str] = field(default_factory=list)


class GenerationEngine:
    def __init__(self, groq_client: GroqClient | None = None):
        self.groq_client = groq_client or GroqClient()

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
        problems = validate_request_combination(request)
        if problems:
            raise InvalidRequestError("; ".join(problems))

        accepted: list[Question] = []
        report = GenerationReport(requested_count=request.count, returned_count=0, attempts=0)

        remaining = request.count
        max_attempts = settings.max_regeneration_retries + 1

        for attempt in range(1, max_attempts + 1):
            report.attempts = attempt
            if remaining <= 0:
                break

            batch_request = request.model_copy(update={"count": remaining})
            raw_items = await self._call_groq(batch_request)

            candidates: list[Question] = []
            for raw in raw_items:
                result = build_question(raw, request)
                if result.error:
                    report.dropped_schema_invalid += 1
                    logger.warning("Schema validation failed, dropping item: %s", result.error)
                    continue
                candidates.append(result.question)

            # marks-vs-answer-length check
            surviving: list[Question] = []
            for q in candidates:
                format_problems = check_marks_format(q) + check_answer_relevance(q)
                if format_problems:
                    report.dropped_marks_format_invalid += 1
                    logger.warning(
                        "Marks-format check failed, dropping item %r: %s",
                        q.text[:60],
                        format_problems,
                    )
                    continue
                surviving.append(q)

            # duplicate check, against everything accepted so far too
            combined = accepted + surviving
            dup_indices = find_duplicates(combined)
            new_dup_indices = {i - len(accepted) for i in dup_indices if i >= len(accepted)}
            report.dropped_duplicates += len(new_dup_indices)
            surviving = [q for i, q in enumerate(surviving) if i not in new_dup_indices]

            for q in surviving:
                warning = flag_difficulty_mismatch(q)
                if warning:
                    report.difficulty_warnings.append(f"{q.id}: {warning}")

            accepted.extend(surviving[: remaining])
            remaining = request.count - len(accepted)

        report.returned_count = len(accepted)

        if len(accepted) < request.count:
            raise GenerationValidationError(
                f"Only produced {len(accepted)}/{request.count} valid questions "
                f"after {report.attempts} attempt(s). "
                f"Dropped: {report.dropped_schema_invalid} schema-invalid, "
                f"{report.dropped_marks_format_invalid} marks-format-invalid, "
                f"{report.dropped_duplicates} duplicates.",
                context={"report": report},
            )

        return accepted, report

    async def _call_groq(self, request: GenerationRequest) -> list[dict]:
        system_prompt, user_prompt = build_prompt(request)
        return await self.groq_client.complete_json(system_prompt, user_prompt)
