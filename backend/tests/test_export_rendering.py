"""
Direct unit coverage for the export renderers (app/services/export/html.py
and renderer.py), which the existing API-level export tests only exercise
through the default ReportLab path.

These call the paper -> HTML / paper -> PDF functions directly against a
fully-loaded `Paper` ORM row (fetched after creating it through the API), so
they don't depend on WeasyPrint actually being installed.
"""
from __future__ import annotations

import sys
import types
import uuid

import pytest

from app.errors import NotFoundError, ServiceUnavailableError
from app.services.export import html as html_service
from app.services.export import renderer as renderer_service

from .conftest import generate_questions

pytestmark = pytest.mark.asyncio


async def _load_paper(client, db_session, *, count=2, marks=3, type="Short"):
    """Create a paper through the API, then fetch the ORM row with its
    relationships loaded (Paper.items / .subject are eager-loaded, so a
    plain get() is enough)."""
    from app.models import Paper

    questions = await generate_questions(client, count=count, marks=marks, type=type)
    response = await client.post(
        "/papers",
        json={
            "title": "Rendering Test Paper",
            "subject": "Science",
            "question_ids": [q["id"] for q in questions],
        },
    )
    assert response.status_code == 201, response.text
    paper_id = uuid.UUID(response.json()["id"])
    paper = await db_session.get(Paper, paper_id)
    assert paper is not None
    return paper


# --- html.py -----------------------------------------------------------


async def test_render_paper_html_contains_expected_structure(client, db_session):
    paper = await _load_paper(client, db_session, count=2, marks=3, type="Short")

    out = html_service.render_paper_html(paper)

    assert out.startswith("<!DOCTYPE html>")
    assert "Karnataka State Board" in out
    assert "Rendering Test Paper" in out
    assert "Answer Key" in out
    assert "Subject: Science" in out
    # Two questions numbered 1. and 2.
    assert "<span class='q-num'>1.</span>" in out
    assert "<span class='q-num'>2.</span>" in out


async def test_render_paper_html_without_answer_key(client, db_session):
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")
    out = html_service.render_paper_html(paper, include_answer_key=False)
    assert "Answer Key" not in out


async def test_render_paper_html_mcq_options_are_lettered(client, db_session):
    paper = await _load_paper(client, db_session, count=1, marks=1, type="MCQ")
    out = html_service.render_paper_html(paper)
    assert "<ul class='options'>" in out
    assert "(a)" in out


async def test_render_paper_html_instructions_vary_by_type(client, db_session):
    mcq_paper = await _load_paper(client, db_session, count=1, marks=1, type="MCQ")
    long_paper = await _load_paper(client, db_session, count=1, marks=5, type="Long")

    mcq_html = html_service.render_paper_html(mcq_paper)
    long_html = html_service.render_paper_html(long_paper)

    assert "write the letter of the correct option" in mcq_html
    assert "write the letter of the correct option" not in long_html
    assert "Answer long-answer questions in full" in long_html


async def test_render_paper_html_escapes_unsafe_text(client, db_session):
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")
    paper.title = "<script>alert('x')</script>"
    out = html_service.render_paper_html(paper)
    assert "<script>alert" not in out
    assert "&lt;script&gt;" in out


# --- renderer.py: branch coverage for the backend-selection logic ------


async def test_active_renderer_reports_explicit_choice(monkeypatch):
    monkeypatch.setattr(renderer_service.settings, "pdf_renderer", "reportlab")
    assert renderer_service.active_renderer() == "reportlab"


async def test_active_renderer_auto_falls_back_without_weasyprint(monkeypatch):
    monkeypatch.setattr(renderer_service.settings, "pdf_renderer", "auto")
    monkeypatch.setattr(renderer_service, "weasyprint_available", lambda: False)
    assert renderer_service.active_renderer() == "reportlab"


async def test_render_pdf_explicit_reportlab_matches_default(client, db_session):
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")
    renderer_service.settings.pdf_renderer = "reportlab"
    try:
        pdf_bytes = renderer_service.render_pdf(paper)
    finally:
        renderer_service.settings.pdf_renderer = "auto"
    assert pdf_bytes.startswith(b"%PDF-")


async def test_render_pdf_weasyprint_requested_but_unavailable(client, db_session):
    """PDF_RENDERER=weasyprint with the library not importable -> 503."""
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")
    assert renderer_service.weasyprint_available() is False, (
        "This test assumes WeasyPrint is not installed in the test env; "
        "if it is, the explicit-unavailable branch can't be exercised here."
    )
    renderer_service.settings.pdf_renderer = "weasyprint"
    try:
        with pytest.raises(ServiceUnavailableError):
            renderer_service.render_pdf(paper)
    finally:
        renderer_service.settings.pdf_renderer = "auto"


async def test_render_pdf_auto_prefers_weasyprint_when_available(
    client, db_session, monkeypatch
):
    """Exercises the `auto` + WeasyPrint-available success path without
    requiring the real WeasyPrint system libraries."""
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")

    monkeypatch.setattr(renderer_service, "weasyprint_available", lambda: True)
    monkeypatch.setattr(
        renderer_service, "_render_weasyprint", lambda p: b"%PDF-fake-weasyprint"
    )
    renderer_service.settings.pdf_renderer = "auto"
    out = renderer_service.render_pdf(paper)
    assert out == b"%PDF-fake-weasyprint"


async def test_render_pdf_auto_falls_back_when_weasyprint_raises(
    client, db_session, monkeypatch
):
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")

    def _boom(_paper):
        raise RuntimeError("weasyprint blew up")

    monkeypatch.setattr(renderer_service, "weasyprint_available", lambda: True)
    monkeypatch.setattr(renderer_service, "_render_weasyprint", _boom)
    renderer_service.settings.pdf_renderer = "auto"
    out = renderer_service.render_pdf(paper)
    # Falls through to the real ReportLab backend.
    assert out.startswith(b"%PDF-")


async def test_resolve_download_rejects_a_filename_outside_the_allowlist():
    """Direct unit test of the filename allowlist itself (app/services/export
    /__init__.py), independent of whether the ASGI router even lets a
    slash-bearing path segment reach the handler."""
    from app.services import export as export_service

    with pytest.raises(NotFoundError):
        export_service.resolve_download("not-a-pdf.txt")

    with pytest.raises(NotFoundError):
        export_service.resolve_download("shouting.PDF")


async def test_weasyprint_available_reflects_import_success(monkeypatch):
    """Simulate WeasyPrint being importable, without needing the real
    package (and its system libraries) installed."""
    fake_module = types.ModuleType("weasyprint")
    monkeypatch.setitem(sys.modules, "weasyprint", fake_module)
    assert renderer_service.weasyprint_available() is True


async def test_reportlab_refuses_kannada_without_a_unicode_font(
    client, db_session, monkeypatch
):
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")
    monkeypatch.setattr(renderer_service, "_needs_kannada", lambda p: True)
    monkeypatch.setattr(
        renderer_service, "_register_fonts", lambda: {"body": "Helvetica", "bold": "Helvetica-Bold", "kannada": ""}
    )
    with pytest.raises(ServiceUnavailableError):
        renderer_service._render_reportlab(paper)
