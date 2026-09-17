"""
Paper builder endpoints (api-contract.md Section 3).

  POST  /papers
  GET   /papers
  GET   /papers/{id}
  PATCH /papers/{id}
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..schemas import ErrorOut, PaperIn, PaperOut, PaperPatch
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
    payload: PaperIn, session: AsyncSession = Depends(get_session)
) -> PaperOut:
    paper = await paper_service.create_paper(session, payload)
    return PaperOut.from_model(paper)


@router.get("", response_model=list[PaperOut], summary="List recent papers")
async def list_papers(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[PaperOut]:
    rows = await paper_service.list_papers(session, limit=limit)
    return [PaperOut.from_model(p) for p in rows]


@router.get(
    "/{paper_id}", response_model=PaperOut, responses={404: {"model": ErrorOut}}
)
async def get_paper(
    paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PaperOut:
    paper = await paper_service.get_paper(session, paper_id)
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
) -> PaperOut:
    paper = await paper_service.update_paper(session, paper_id, payload)
    return PaperOut.from_model(paper)
