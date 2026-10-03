"""
Blueprint-based papers: "Section A is 10 one-mark MCQs, Section B is 5 two-mark
short answers ..., and the paper is 40% Chapter 1, 35% Chapter 2, 25% Chapter 3"
-> a concrete paper.

Two stages, kept apart on purpose:

  1. `build_plan` is pure arithmetic. It decides *how many questions of each
     section come from each chapter*. No database, no LLM, deterministic, so the
     frontend can show it as a preview (POST /papers/blueprint/preview) before
     anything is generated.

  2. `create_blueprint_paper` fetches the questions the plan calls for (stored
     ones first, then LLM generation for the shortfall, via the same code path
     as POST /generate) and stores them as a paper whose questions carry their
     section.

How the marks are split across chapters
---------------------------------------
Every chapter has a target of `weightage% x total marks`. Questions are handed
out largest-marks first, each to the chapter that is currently furthest below
its target. Handing out the big questions first matters: a 5-mark question can
overshoot a small chapter's target, and the 1-mark questions that follow are
what smooth that out again. Because questions are whole units, a chapter can
land a mark or two off its target; the preview reports the achieved figure.

The result is not guaranteed to hit the percentages exactly (a 2-mark section
cannot split 50/50 over three chapters), but it is always as close as whole
questions allow.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from generation_engine.schemas import QuestionType

from ..errors import UnprocessableError
from ..models import Paper, PaperQuestion, Question
from ..schemas.requests import BlueprintIn, GenerateIn
from ..schemas.responses import (
    BlueprintAllocationOut,
    BlueprintChapterPlanOut,
    BlueprintPlanOut,
    BlueprintSectionPlanOut,
)
from . import generation as generation_service
from .papers import compute_total_marks
from .syllabus import get_or_create_subject

logger = logging.getLogger("backend.blueprint")

# generation_engine caps one request at 25 questions (MAX_BATCH_COUNT).
_BATCH = 25
# Extra rounds to top up a group that came back short (e.g. the engine dropped
# a near-duplicate). Each round asks only for what is still missing.
_TOP_UP_ROUNDS = 2

_MIXED_CYCLE = ("easy", "medium", "hard")


@dataclass
class Plan:
    """The allocation, plus the per-slot detail the builder needs."""

    # sections[i] -> chapter name for each question slot, in paper order
    slots: list[list[str]] = field(default_factory=list)
    response: BlueprintPlanOut | None = None


def build_plan(blueprint: BlueprintIn) -> Plan:
    total_marks = blueprint.total_marks
    chapters = [c.name for c in blueprint.chapters]
    weights = {c.name: c.weightage for c in blueprint.chapters}
    target = {name: weights[name] / 100 * total_marks for name in chapters}
    assigned = {name: 0 for name in chapters}

    # (section index, marks) for every question in the paper, biggest first.
    # `sorted` is stable, so equal-mark slots stay in section order.
    work = sorted(
        (
            (si, section.marks_per_question)
            for si, section in enumerate(blueprint.sections)
            for _ in range(section.question_count)
        ),
        key=lambda item: -item[1],
    )

    per_section: list[dict[str, int]] = [
        {name: 0 for name in chapters} for _ in blueprint.sections
    ]
    for si, marks in work:
        # Largest shortfall wins; ties go to the heavier chapter, then to the
        # chapter listed first, so the result never depends on dict order.
        pick = max(
            range(len(chapters)),
            key=lambda i: (
                target[chapters[i]] - assigned[chapters[i]],
                weights[chapters[i]],
                -i,
            ),
        )
        name = chapters[pick]
        assigned[name] += marks
        per_section[si][name] += 1

    plan = Plan()
    section_plans: list[BlueprintSectionPlanOut] = []
    planned_questions = {name: 0 for name in chapters}
    for si, section in enumerate(blueprint.sections):
        counts = per_section[si]
        # Within a section, questions are grouped by chapter in the order the
        # chapters were listed.
        slots = [name for name in chapters for _ in range(counts[name])]
        plan.slots.append(slots)
        for name in chapters:
            planned_questions[name] += counts[name]
        section_plans.append(
            BlueprintSectionPlanOut(
                name=section.name,
                type=section.type,
                marks_per_question=section.marks_per_question,
                difficulty=section.difficulty,
                questions=section.question_count,
                marks=section.total_marks,
                allocations=[
                    BlueprintAllocationOut(
                        chapter=name,
                        questions=counts[name],
                        marks=counts[name] * section.marks_per_question,
                    )
                    for name in chapters
                    if counts[name]
                ],
            )
        )

    plan.response = BlueprintPlanOut(
        total_marks=total_marks,
        total_questions=sum(s.question_count for s in blueprint.sections),
        sections=section_plans,
        chapters=[
            BlueprintChapterPlanOut(
                chapter=name,
                weightage=weights[name],
                target_marks=round(target[name], 2),
                planned_marks=assigned[name],
                planned_questions=planned_questions[name],
            )
            for name in chapters
        ],
    )
    return plan


def _slot_difficulties(blueprint: BlueprintIn, plan: Plan) -> list[list[str]]:
    """Difficulty for each slot. 'mixed' cycles easy/medium/hard down the section."""
    out: list[list[str]] = []
    for section, slots in zip(blueprint.sections, plan.slots):
        if section.difficulty == "mixed":
            out.append([_MIXED_CYCLE[i % 3] for i in range(len(slots))])
        else:
            out.append([section.difficulty] * len(slots))
    return out


async def _fetch_group(
    session: AsyncSession,
    blueprint: BlueprintIn,
    *,
    chapter: str,
    q_type: QuestionType,
    marks: int,
    difficulty: str,
    count: int,
    user_id: uuid.UUID,
    on_progress: Callable[[int], None] | None = None,
) -> list[Question]:
    """`count` distinct questions for one (chapter, type, marks, difficulty).

    Goes through POST /generate's own service, so stored questions are reused
    and only the shortfall is generated. Raises 422 if it cannot find enough.
    """
    got: list[Question] = []
    seen: set[uuid.UUID] = set()

    async def ask(n: int, refresh: bool) -> None:
        payload = GenerateIn(
            subject=blueprint.subject,
            chapter=chapter,
            type=q_type,
            grade=blueprint.grade,
            marks=marks,
            difficulty=difficulty,
            count=n,
            refresh=refresh,
        )
        rows, *_ = await generation_service.generate_questions(
            session, payload, user_id=user_id
        )
        before = len(got)
        for row in rows:
            if row.id not in seen and len(got) < count:
                seen.add(row.id)
                got.append(row)
        if on_progress is not None and len(got) > before:
            on_progress(len(got) - before)

    # The first request honours the caller's `refresh`, so it may be served from
    # storage. Every later request forces fresh generation: asking the cache
    # again would just return the rows already in `got`.
    refresh = blueprint.refresh
    rounds = 0
    max_rounds = -(-count // _BATCH) + _TOP_UP_ROUNDS
    while len(got) < count and rounds < max_rounds:
        await ask(min(_BATCH, count - len(got)), refresh)
        refresh = True
        rounds += 1

    if len(got) < count:
        raise UnprocessableError(
            f"Could only find {len(got)} of {count} distinct {marks}-mark "
            f'{q_type.value} questions for "{chapter}". Try again, or reduce '
            f"the number of questions drawn from this chapter."
        )
    return got


async def create_blueprint_paper(
    session: AsyncSession,
    blueprint: BlueprintIn,
    user_id: uuid.UUID,
    on_progress: Callable[[int, int], None] | None = None,
) -> Paper:
    """Build and store the paper.

    `on_progress(done, total)` is called with the number of questions gathered so
    far (stored or newly generated) out of the number the paper needs, once at the
    start and again after every batch. It is what the background job reports.
    """
    plan = build_plan(blueprint)
    difficulties = _slot_difficulties(blueprint, plan)

    # Fold every slot into (chapter, type, marks, difficulty) groups, so two
    # sections that ask for the same kind of question share one fetch instead of
    # each fetching (and possibly colliding on) the same stored rows.
    GroupKey = tuple[str, QuestionType, int, str]
    needed: dict[GroupKey, int] = {}
    slot_keys: list[list[GroupKey]] = []
    for section, slots, diffs in zip(blueprint.sections, plan.slots, difficulties):
        keys = [
            (chapter, section.type, section.marks_per_question, diff)
            for chapter, diff in zip(slots, diffs)
        ]
        slot_keys.append(keys)
        for key in keys:
            needed[key] = needed.get(key, 0) + 1

    # Sequential on purpose: every call writes through the same request-scoped
    # session, and each may be a slow LLM call. A failure anywhere rolls the
    # whole request back, so a paper is either complete or not stored at all.
    total = sum(needed.values())
    gathered = 0

    def report(delta: int = 0) -> None:
        nonlocal gathered
        gathered = min(total, gathered + delta)
        if on_progress is not None:
            on_progress(gathered, total)

    report()
    pools: dict[GroupKey, list[Question]] = {}
    for key, count in needed.items():
        chapter, q_type, marks, difficulty = key
        pools[key] = await _fetch_group(
            session,
            blueprint,
            chapter=chapter,
            q_type=q_type,
            marks=marks,
            difficulty=difficulty,
            count=count,
            user_id=user_id,
            on_progress=report,
        )

    subject_row = await get_or_create_subject(session, blueprint.subject)
    title = blueprint.title or f"{blueprint.subject.value} Question Paper (Grade {blueprint.grade})"
    paper = Paper(title=title, subject_id=subject_row.id, user_id=user_id, total_marks=0)
    session.add(paper)
    await session.flush()

    order = 0
    for section, keys in zip(blueprint.sections, slot_keys):
        for key in keys:
            question = pools[key].pop(0)
            session.add(
                PaperQuestion(
                    paper_id=paper.id,
                    question_id=question.id,
                    order_index=order,
                    section=section.name,
                )
            )
            order += 1
    await session.flush()
    await session.refresh(paper, attribute_names=["items", "subject"])

    paper.total_marks = compute_total_marks(paper)
    await session.flush()
    logger.info(
        "Blueprint paper %s: %d questions, %d marks, %d sections",
        paper.id,
        order,
        paper.total_marks,
        len(blueprint.sections),
    )
    return paper
