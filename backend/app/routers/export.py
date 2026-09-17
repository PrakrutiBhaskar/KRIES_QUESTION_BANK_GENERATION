"""
Export endpoints (api-contract.md Section 4).

  POST /export/{paper_id}         -> {"download_url": ...}
  GET  /export/files/{filename}   -> the PDF itself

The second route isn't in the contract — it's the thing `download_url` points
at. It's listed here so the frontend can see it in the OpenAPI schema.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..schemas import ErrorOut, ExportOut
from ..services import export as export_service
from ..services import papers as paper_service

router = APIRouter(prefix="/export", tags=["export"])


@router.post(
    "/{paper_id}",
    response_model=ExportOut,
    summary="Compile a paper into a downloadable PDF",
    responses={404: {"model": ErrorOut}, 503: {"model": ErrorOut}},
)
async def export_paper(
    paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ExportOut:
    paper = await paper_service.get_paper(session, paper_id)
    path, size = export_service.export_paper(paper)
    return ExportOut(
        download_url=export_service.public_url(path.name),
        filename=path.name,
        size_bytes=size,
    )


@router.get(
    "/files/{filename}",
    response_class=FileResponse,
    summary="Download a previously exported PDF",
    responses={404: {"model": ErrorOut}},
)
async def download_export(filename: str) -> FileResponse:
    path = export_service.resolve_download(filename)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        # `inline` lets the web target preview in a browser tab; the Android
        # target ignores it and saves the file.
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )
