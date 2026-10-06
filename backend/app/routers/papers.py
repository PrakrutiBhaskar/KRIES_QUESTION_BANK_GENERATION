"""
Paper builder endpoints (api-contract.md Section 3).

  POST  /papers
  GET   /papers
  GET   /papers/{id}
  PATCH /papers/{id}
  DELETE /papers/{id}     (not in the original contract; added for the frontend)
  POST  /papers/blueprint           build a board-style paper from a blueprint
  POST  /papers/blueprint/preview   the same allocation, without generating anything
  POST  /papers/blueprint/jobs      start the same build in the background (202)
  GET   /papers/blueprint/jobs/{id} progress: questions gathered so far, then the paper
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user, require_generator
from ..models import User
from ..schemas import BlueprintIn, BlueprintJobOut, BlueprintPlanOut, ErrorOut, PaperIn, PaperOut, PaperPatch
from ..services import blueprint as blueprint_service
from ..services import blueprint_jobs
from ..services import papers as paper_service

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post(
    "",
    response_model=PaperOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a paper from selected questions",
    responses={400: {"model": ErrorOut}},
)
async def create_paper(
    payload: PaperIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PaperOut:
    paper = await paper_service.create_paper(session, payload, user.id)
    return PaperOut.from_model(paper)


@router.post(
    "/blueprint",
    response_model=PaperOut,
    status_code=status.HTTP_201_CREATED,
    summary="Build a paper from a blueprint (marks per section, weightage per chapter)",
    description=(
        "Sections say what kind of question fills them and how many marks they "
        "carry; chapters say what share of the paper's marks they get. Stored "
        "questions are reused and the rest are generated, so this can take a "
        "while. It is all-or-nothing: on any failure no paper and no new "
        "questions are stored."
    ),
    responses={
        400: {"model": ErrorOut},
        422: {"model": ErrorOut},
        429: {"model": ErrorOut},
        502: {"model": ErrorOut},
    },
)
async def create_blueprint_paper(
    payload: BlueprintIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_generator),
) -> PaperOut:
    paper = await blueprint_service.create_blueprint_paper(session, payload, user.id)
    return PaperOut.from_model(paper)


@router.post(
    "/blueprint/jobs",
    response_model=BlueprintJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Build a paper from a blueprint in the background",
    description=(
        "Same build as `POST /papers/blueprint` (all-or-nothing, stored questions "
        "reused), but it answers at once with a job id. Poll "
        "`GET /papers/blueprint/jobs/{id}` for `done` / `total` questions and, when "
        "`status` is `done`, the finished paper. One build per user at a time (409)."
    ),
    responses={400: {"model": ErrorOut}, 409: {"model": ErrorOut}, 429: {"model": ErrorOut}},
)
async def start_blueprint_job(
    payload: BlueprintIn, user: User = Depends(require_generator)
) -> BlueprintJobOut:
    # Same arithmetic as the preview, so an impossible blueprint is a 400 now
    # rather than an error found halfway through.
    blueprint_service.build_plan(payload)
    return blueprint_jobs.start(payload, user.id).to_out()


@router.get(
    "/blueprint/jobs/{job_id}",
    response_model=BlueprintJobOut,
    summary="Progress of a background paper build",
    responses={404: {"model": ErrorOut}},
)
async def get_blueprint_job(
    job_id: uuid.UUID, user: User = Depends(get_current_user)
) -> BlueprintJobOut:
    return blueprint_jobs.get(job_id, user.id).to_out()


@router.post(
    "/blueprint/preview",
    response_model=BlueprintPlanOut,
    summary="Show how a blueprint would be split across chapters, without generating",
    responses={400: {"model": ErrorOut}},
)
async def preview_blueprint(payload: BlueprintIn) -> BlueprintPlanOut:
    plan = blueprint_service.build_plan(payload)
    assert plan.response is not None
    return plan.response


@router.get("", response_model=list[PaperOut], summary="List your recent papers")
async def list_papers(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[PaperOut]:
    rows = await paper_service.list_papers(session, user.id, limit=limit)
    return [PaperOut.from_model(p) for p in rows]


@router.get(
    "/{paper_id}", response_model=PaperOut, responses={404: {"model": ErrorOut}}
)
async def get_paper(
    paper_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PaperOut:
    paper = await paper_service.get_paper(session, paper_id, user.id)
    return PaperOut.from_model(paper)


@router.patch(
    "/{paper_id}",
    response_model=PaperOut,
    summary="Reorder questions, override marks, or rename",
    responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
async def patch_paper(
    paper_id: uuid.UUID,
    payload: PaperPatch,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PaperOut:
    paper = await paper_service.update_paper(session, paper_id, payload, user.id)
    return PaperOut.from_model(paper)


@router.delete(
    "/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a paper (its questions stay in the question pool)",
    responses={404: {"model": ErrorOut}},
)
async def delete_paper(
    paper_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    await paper_service.delete_paper(session, paper_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
