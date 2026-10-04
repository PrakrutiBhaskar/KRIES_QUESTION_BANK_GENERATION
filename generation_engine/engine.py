"""
GenerationEngine — the Module A entry point.

Orchestrates: request validation -> prompt building -> Groq call -> schema
validation -> duplicate check -> marks-format check -> retry-to-fill on
failures -> a clean batch of exactly `request.count` validated Questions.

Answer-key verification (rule checks + an independent AI pass) is NOT part of
generation. It is a separate, on-demand step: `verify_answers()` below, which
Module B exposes as `POST /questions/verify` and the UI triggers from a
"Verify answers" button once questions have been generated.

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

from .answer_verification import FLAGGED, REJECTED, verify_questions
from .config import settings
from .difficulty import flag_difficulty_mismatch
from .exceptions import GenerationValidationError, GroqAPIError, InvalidRequestError
from .groq_client import GroqClient
from .prompts import build_prompt
from .schemas import GenerationRequest, Question
from .syllabus import SyllabusIndex
from .textbook import Passage, TextbookCorpus, select_passages
from .validation import (
    build_question,
    check_answer_relevance,
    check_board_scope,
    check_figure_question,
    check_grounding,
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
    dropped_out_of_syllabus: int = 0
    dropped_ungrounded: int = 0
    passages_total: int = 0
    passages_used: list[str] = field(default_factory=list)
    dropped_figure_invalid: int = 0  # figure questions that contradicted their metadata
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
            "dropped_out_of_syllabus": self.dropped_out_of_syllabus,
            "dropped_ungrounded": self.dropped_ungrounded,
            "passages_total": self.passages_total,
            "passages_used": list(self.passages_used),
            "dropped_figure_invalid": self.dropped_figure_invalid,
            "difficulty_warnings": list(self.difficulty_warnings),
            "rejection_reasons": list(self.rejection_reasons),
        }


class GenerationEngine:
    def __init__(
        self,
        groq_client: GroqClient | None = None,
        syllabus: Optional[SyllabusIndex] = None,
        textbooks: Optional[TextbookCorpus] = None,
        require_textbook: Optional[bool] = None,
        verifier_client: GroqClient | None = None,
    ):
        self.groq_client = groq_client or GroqClient()
        self.textbooks = textbooks
        # With a textbook corpus and no explicit index, the textbooks ARE the
        # syllabus: chapters/grades/topics are derived from them, not listed.
        if syllabus is None and textbooks is not None and not textbooks.is_empty():
            syllabus = SyllabusIndex.from_dict(textbooks.to_syllabus_dict())
        self.syllabus = syllabus
        self.require_textbook = (
            settings.require_textbook if require_textbook is None else require_textbook
        )
        # The second AI pass, run only when `verify_answers()` is called. A different model gives a more independent opinion
        # (VERIFIER_MODEL); when the caller supplied their own client, or no
        # separate model is configured, the generating client does both jobs.
        if verifier_client is not None:
            self.verifier_client = verifier_client
        elif settings.verifier_model and groq_client is None:
            self.verifier_client = GroqClient(model=settings.verifier_model)
        else:
            self.verifier_client = self.groq_client

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
        problems = validate_request_combination(
            request,
            syllabus=self.syllabus,
            require_syllabus=settings.require_syllabus,
        )
        if problems:
            raise InvalidRequestError("; ".join(problems))

        all_passages: list[Passage] = []
        # Figure requests are written from the figures' own metadata, not from
        # textbook passages (the two are different grounding sources), so they
        # skip passage selection and the textbook requirement.
        if self.textbooks is not None and not request.figures:
            all_passages = self.textbooks.passages(
                request.subject, request.grade, request.chapter, topic=request.topic
            )
        if not all_passages and self.require_textbook and not request.figures:
            raise InvalidRequestError(
                "no Karnataka State Board textbook text has been ingested for "
                f'{request.subject.value} Class {request.grade}, chapter '
                f'"{request.chapter}". Ingest the KTBS textbook PDF '
                "(scripts/ingest_textbooks.py) before generating."
            )
        issued = 0  # passages handed out so far; retries move on to fresh ones

        accepted: list[Question] = []
        report = GenerationReport(
            requested_count=request.count, returned_count=0, attempts=0
        )
        report.passages_total = len(all_passages)

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
            batch_passages = select_passages(
                all_passages, remaining, request.coverage_offset + issued
            )
            issued += len(batch_passages)
            raw_items = await self._call_groq(batch_request, feedback, batch_passages)

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
                q = result.question
                if batch_passages:
                    src = self._source_passage(result.raw, batch_passages)
                    texts = [src.text] if src else [p.text for p in batch_passages]
                    problems = check_grounding(
                        q, texts, settings.grounding_min_overlap
                    )
                    if problems:
                        report.dropped_ungrounded += 1
                        feedback.append("; ".join(problems))
                        report.rejection_reasons.append("; ".join(problems))
                        logger.warning(
                            "Grounding check failed, dropping item %r", q.text[:60]
                        )
                        continue
                    if src:
                        q.tags = [*q.tags, f"src:{src.id}"]
                        if not q.topic:
                            q.topic = src.section
                        if src.id not in report.passages_used:
                            report.passages_used.append(src.id)
                candidates.append(q)

            # marks-vs-answer-length + relevance + figure-metadata + board-scope checks
            surviving: list[Question] = []
            for q in candidates:
                scope_problems = check_board_scope(q)
                format_problems = check_marks_format(q)
                relevance_problems = check_answer_relevance(q)
                figure_problems = check_figure_question(q, request)
                if scope_problems or format_problems or relevance_problems or figure_problems:
                    if scope_problems:
                        report.dropped_out_of_syllabus += 1
                    elif format_problems:
                        report.dropped_marks_format_invalid += 1
                    elif relevance_problems:
                        report.dropped_irrelevant += 1
                    else:
                        report.dropped_figure_invalid += 1
                    joined = "; ".join(
                        scope_problems + format_problems + relevance_problems + figure_problems
                    )
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
                f"{report.dropped_out_of_syllabus} out-of-syllabus, "
                f"{report.dropped_ungrounded} ungrounded, "
                f"{report.dropped_figure_invalid} contradicting their figure, "
                f"{report.dropped_duplicates} duplicates.",
                context={"report": report.as_dict()},
            )

        return accepted, report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _call_groq(
        self,
        request: GenerationRequest,
        feedback: list[str] | None = None,
        passages: list[Passage] | None = None,
    ) -> list[dict]:
        topics = (
            self.syllabus.topics(request.subject, request.chapter)
            if self.syllabus is not None and not passages
            else None
        )
        system_prompt, user_prompt = build_prompt(
            request,
            retry_feedback=feedback,
            chapter_topics=topics,
            passages=passages or None,
            max_passage_chars=settings.max_passage_chars,
        )
        return await self.groq_client.complete_json(system_prompt, user_prompt)

    @staticmethod
    def _source_passage(raw: dict, passages: list[Passage]) -> Passage | None:
        """The passage the model says it used (1-based "passage"), if valid."""
        try:
            idx = int(raw.get("passage"))
        except (TypeError, ValueError):
            return None
        return passages[idx - 1] if 1 <= idx <= len(passages) else None

    async def verify_answers(self, questions: list[Question]) -> list[Question]:
        """
        Check the answer keys of already-generated questions (on demand).

        Rule checks first, then an independent AI pass for whatever the rules
        could not decide (see answer_verification.py). Returns one copy of each
        input question, in order, stamped with `verification_status`:

          verified    a rule confirmed the key, or the AI pass reached the same answer
          unverified  nothing could be checked (no rule applies, the AI pass was
                      not confident, or it failed)
          flagged     a rule or the AI pass found the key wrong

        Never raises: an AI-pass failure just leaves questions "unverified".
        Unlike generation, nothing is dropped or regenerated here — a flagged
        question is reported to the teacher, who can regenerate or delete it.
        """
        if not questions:
            return []
        results = await verify_questions(
            questions,
            client=self.verifier_client,
            use_rules=settings.enable_answer_rule_checks,
            use_llm=settings.enable_llm_answer_verification,
            chunk_size=settings.verification_chunk_size,
        )
        out: list[Question] = []
        for q, result in zip(questions, results):
            status = FLAGGED if result.status == REJECTED else result.status
            if status == FLAGGED:
                logger.warning("Answer verification flagged %r: %s", q.text[:60], result.note)
            out.append(
                q.model_copy(
                    update={"verification_status": status, "verification_note": result.note}
                )
            )
        return out

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
