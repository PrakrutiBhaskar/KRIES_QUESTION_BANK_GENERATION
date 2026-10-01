"""
Export endpoints (api-contract.md Section 4).

  POST /export/{paper_id}         -> {"download_url": ...}   (signed in, your paper)
  GET  /export/files/{filename}   -> the PDF itself          (signed link)

The second route isn't in the contract — it's the thing `download_url` points
at. It is opened in a new browser tab, which can't send an Authorization
header, so instead of a bearer token it requires the short-lived `?token=`
that POST /export/{paper_id} put in the URL (valid for 10 minutes, for that
one file only).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..errors import UnauthorizedError
from ..models import User
from ..schemas import ErrorOut, ExportOut
from ..security import create_download_token, verify_download_token
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
    paper_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ExportOut:
    paper = await paper_service.get_paper(session, paper_id, user.id)
    path, size = export_service.export_paper(paper)
    return ExportOut(
        download_url=export_service.public_url(
            path.name, token=create_download_token(path.name)
        ),
        filename=path.name,
        size_bytes=size,
    )


@router.get(
    "/files/{filename}",
    response_class=FileResponse,
    summary="Download a previously exported PDF",
    responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
async def download_export(
    filename: str, token: str | None = Query(default=None)
) -> FileResponse:
    if not token or not verify_download_token(token, filename):
        raise UnauthorizedError(
            "This download link is invalid or has expired. Export the paper again.",
            error="invalid_download_token",
        )
    path = export_service.resolve_download(filename)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        # `inline` lets the web target preview in a browser tab; the Android
        # target ignores it and saves the file.
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )
