"""
Paper builder (teacher flow, spec.md Section 3).

Two rules carry most of the weight here:

  * `total_marks` is always recomputed from the paper's questions, using
    `marks_override` where set. The client may send its own figure on POST;
    if it disagrees with the computed total that's a 400, so a stale frontend
    total is caught rather than silently stored.

  * Order is dense and zero-based. Whatever `order_index` values the client
    sends on PATCH, they're sorted and renumbered 0..n-1 before storing, so a
    drag-and-drop UI can send whatever it likes without the gaps compounding.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import BadRequestError, NotFoundError
from ..models import Paper, PaperQuestion, Question
from ..schemas.requests import PaperIn, PaperPatch
from . import questions as question_service
from .syllabus import get_or_create_subject


def compute_total_marks(paper: Paper) -> int:
    return sum(item.effective_marks for item in paper.items)


async def _load(session: AsyncSession, paper_id: uuid.UUID) -> Paper:
    paper = await session.scalar(select(Paper).where(Paper.id == paper_id))
    if paper is None:
        raise NotFoundError(f"Paper {paper_id} not found.")
    return paper


async def create_paper(session: AsyncSession, payload: PaperIn) -> Paper:
    found = await question_service.get_questions_by_ids(session, payload.question_ids)

    missing = [str(qid) for qid in payload.question_ids if qid not in found]
    if missing:
        raise BadRequestError(
            f"Unknown or discarded question_ids: {', '.join(missing)}"
        )

    # A paper belongs to one subject; mixing subjects would break both the
    # export header and the marks scheme the questions were generated under.
    wrong_subject = [
        str(qid)
        for qid in payload.question_ids
        if found[qid].subject.name != payload.subject.value
    ]
    if wrong_subject:
        raise BadRequestError(
            f"These questions do not belong to {payload.subject.value}: "
            f"{', '.join(wrong_subject)}"
        )

    subject_row = await get_or_create_subject(session, payload.subject)
    paper = Paper(
        title=payload.title.strip(),
        subject_id=subject_row.id,
        user_id=payload.user_id,
        total_marks=0,
    )
    session.add(paper)
    await session.flush()

    # Order follows the order the ids arrived in — that's the order the
    # teacher selected them in.
    for order, qid in enumerate(payload.question_ids):
        session.add(
            PaperQuestion(paper_id=paper.id, question_id=qid, order_index=order)
        )
    await session.flush()
    await session.refresh(paper, attribute_names=["items", "subject"])

    computed = compute_total_marks(paper)
    if payload.total_marks is not None and payload.total_marks != computed:
        raise BadRequestError(
            f"total_marks {payload.total_marks} does not match the sum of the "
            f"selected questions ({computed}). Omit the field to let the "
            f"server compute it."
        )

    paper.total_marks = computed
    await session.flush()
    return paper


async def get_paper(session: AsyncSession, paper_id: uuid.UUID) -> Paper:
    return await _load(session, paper_id)


async def update_paper(
    session: AsyncSession, paper_id: uuid.UUID, payload: PaperPatch
) -> Paper:
    paper = await _load(session, paper_id)

    if payload.title is not None:
        paper.title = payload.title.strip()

    if payload.questions is not None:
        ids = [item.question_id for item in payload.questions]
        found = await question_service.get_questions_by_ids(session, ids)
        missing = [str(qid) for qid in ids if qid not in found]
        if missing:
            raise BadRequestError(
                f"Unknown or discarded question_ids: {', '.join(missing)}"
            )
        wrong_subject = [
            str(qid)
            for qid in ids
            if found[qid].subject_id != paper.subject_id
        ]
        if wrong_subject:
            raise BadRequestError(
                f"These questions do not belong to this paper's subject: "
                f"{', '.join(wrong_subject)}"
            )

        existing = {item.question_id: item for item in paper.items}
        ordered = sorted(payload.questions, key=lambda i: i.order_index)

        for position, item in enumerate(ordered):
            row = existing.pop(item.question_id, None)
            if row is None:
                row = PaperQuestion(paper_id=paper.id, question_id=item.question_id)
                session.add(row)
                paper.items.append(row)
            row.order_index = position  # renumbered dense
            row.marks_override = item.marks_override

        # Anything the client left out has been removed from the paper.
        for stale in existing.values():
            paper.items.remove(stale)
            await session.delete(stale)

        await session.flush()
        await session.refresh(paper, attribute_names=["items"])

    paper.total_marks = compute_total_marks(paper)
    await session.flush()
    await session.refresh(paper, attribute_names=["items", "subject"])
    return paper


async def list_papers(session: AsyncSession, *, limit: int = 50) -> list[Paper]:
    rows = await session.scalars(
        select(Paper).order_by(Paper.created_at.desc()).limit(limit)
    )
    return list(rows.all())
