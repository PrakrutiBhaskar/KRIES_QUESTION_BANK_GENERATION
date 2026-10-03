"""
Figure endpoints: the shared library of diagrams that can be attached to
questions and printed in the paper or the answer key.

  POST   /figures              upload an image            (administrators only)
  GET    /figures              the library, newest first  (any signed-in user)
  GET    /figures/{id}         metadata for one figure    (any signed-in user)
  GET    /figures/{id}/file    the image itself           (any signed-in user)
  PATCH  /figures/{id}         change caption / metadata  (administrators only)
  DELETE /figures/{id}         delete a figure nothing uses (administrators only)

Administrators (`role == "Admin"`) own the library: they upload diagrams, tag
them with a subject / chapter / topic and list the labelled parts. Everyone
signed in can then write questions about them (`POST /generate` with
`use_figures`) and attach them to questions. Mutating routes answer 403
`admin_required` for anyone else. An administrator account is created on the
server with scripts/make_admin.py; it can't be chosen at sign-up.

Besides the caption, a figure carries optional metadata that question
generation works from: `subject`, `chapter`, `topic` and `labels` (the labelled
parts, e.g. "A: nucleus"). The model never sees the image. Administrators and
teachers see the metadata; students don't (the labels are an answer key).

Attaching a figure to a question is `PATCH /questions/{id}` with `figure_id`
(printed with the question) and/or `answer_figure_id` (printed only in the
answer key); send null to detach. A question with only `figure_id` prints that
diagram in the answer key as well.

Not in the original api-contract.md; documented in docs/api-contract.md
Section 6.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import get_current_user, require_admin
from ..errors import NotFoundError, PayloadTooLargeError
from ..models import User
from ..schemas import ErrorOut, FigureDetailOut, FigurePatch, Page
from ..services import figures as figure_service

router = APIRouter(prefix="/figures", tags=["figures"])


@router.post(
    "",
    response_model=FigureDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a figure",
    description=(
        "Accepts a PNG or JPEG (GIF and WebP are converted to PNG). The image is "
        "re-encoded on the server: transparency is flattened onto white, metadata "
        "is removed and very large images are scaled down for print. Administrators "
        "only. Optional form "
        "fields `subject`, `chapter`, `topic` and `labels` (one entry per line, or a "
        "JSON array) describe the figure for question generation."
    ),
    responses={
        400: {"model": ErrorOut, "description": "Not a readable PNG/JPEG"},
        403: {"model": ErrorOut, "description": "Not an administrator"},
        413: {"model": ErrorOut, "description": "Larger than MAX_FIGURE_BYTES"},
    },
)
async def upload_figure(
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    subject: str = Form(default=""),
    chapter: str = Form(default=""),
    topic: str = Form(default=""),
    labels: str = Form(default=""),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> FigureDetailOut:
    # Read one byte past the limit so an oversized upload is rejected without
    # pulling the whole body into memory.
    raw = await file.read(settings.max_figure_bytes + 1)
    if len(raw) > settings.max_figure_bytes:
        raise PayloadTooLargeError(
            f"Image is larger than the {settings.max_figure_bytes / (1024 * 1024):g} MB limit."
        )
    figure = await figure_service.create_figure(
        session,
        raw,
        caption=caption,
        uploaded_by=admin.id,
        subject=subject,
        chapter=chapter,
        topic=topic,
        labels=labels,
    )
    return FigureDetailOut.from_model(figure, viewer_role=admin.role)


@router.get(
    "",
    response_model=Page[FigureDetailOut],
    summary="List the figure library",
    description=(
        "Optional filters narrow the list to one subject / chapter, which is what "
        "the Generate screen uses to show the figures a request would draw on."
    ),
)
async def list_figures(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    subject: str | None = Query(default=None),
    chapter: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Page[FigureDetailOut]:
    rows, total = await figure_service.list_figures(
        session,
        limit=page_size,
        offset=(page - 1) * page_size,
        subject=figure_service.clean_subject(subject),
        chapter=figure_service.clean_short_text(chapter, field="chapter"),
    )
    return Page[FigureDetailOut](
        results=[FigureDetailOut.from_model(r, viewer_role=user.role) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{figure_id}",
    response_model=FigureDetailOut,
    summary="Figure metadata",
    description=(
        "Image details for any signed-in user. The subject, chapter, topic and "
        "labels are included for administrators and teachers, not students."
    ),
    responses={404: {"model": ErrorOut}},
)
async def get_figure(
    figure_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> FigureDetailOut:
    figure = await figure_service.get_figure(session, figure_id)
    return FigureDetailOut.from_model(figure, viewer_role=user.role)


@router.get(
    "/{figure_id}/file",
    response_class=FileResponse,
    summary="The figure image",
    description=(
        "Needs the bearer token like every other route. Any signed-in user can "
        "read a figure, because figures ride along with questions in the shared pool."
    ),
    responses={404: {"model": ErrorOut}},
)
async def figure_file(
    figure_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> FileResponse:
    figure = await figure_service.get_figure(session, figure_id)
    path = figure_service.figure_path(figure)
    if not path.is_file():
        raise NotFoundError("The image file for this figure is missing.")
    return FileResponse(
        path,
        media_type=figure.mime,
        headers={
            # The bytes of a given figure id never change, but the response is
            # behind auth, so keep it out of shared caches.
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch(
    "/{figure_id}",
    response_model=FigureDetailOut,
    summary="Edit a figure's caption and metadata",
    description="Only the fields you send change; send an empty value to clear one.",
    responses={
        400: {"model": ErrorOut, "description": "Unknown subject, too many labels, ..."},
        403: {"model": ErrorOut},
        404: {"model": ErrorOut},
    },
)
async def patch_figure(
    figure_id: uuid.UUID,
    payload: FigurePatch,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> FigureDetailOut:
    figure = await figure_service.update_metadata(
        session, figure_id, payload.model_dump(exclude_unset=True)
    )
    return FigureDetailOut.from_model(figure, viewer_role=admin.role)


@router.delete(
    "/{figure_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a figure from the library",
    responses={
        403: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut, "description": "Still attached to a question"},
    },
)
async def delete_figure(
    figure_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
) -> Response:
    await figure_service.delete_figure(session, figure_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
