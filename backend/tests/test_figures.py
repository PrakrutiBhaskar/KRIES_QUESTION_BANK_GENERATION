"""
Figures: upload and storage, attaching them to questions, and printing them in
the paper and the answer key through all three PDF renderers.
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader
from sqlalchemy import select

from app.config import settings
from app.models import Paper
from app.services import figures as figure_service
from app.services.export import html as html_service
from app.services.export import renderer as renderer_service
from app.services.questions import content_hash

from .conftest import generate_questions

pytestmark = pytest.mark.asyncio


# --- helpers ---------------------------------------------------------------


def make_png(color=(200, 40, 40), size=(400, 300), mode="RGB") -> bytes:
    img = Image.new(mode, size, color)
    ImageDraw.Draw(img).line([(0, 0), size], fill=(0, 0, 0), width=5)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_jpeg(size=(400, 300), exif: bool = False) -> bytes:
    img = Image.new("RGB", size, (30, 120, 200))
    buf = BytesIO()
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCameraMaker"  # Make
        img.save(buf, "JPEG", exif=data)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


async def upload(c, data: bytes, *, name="fig.png", caption="", ctype="image/png"):
    return await c.post(
        "/figures",
        files={"file": (name, data, ctype)},
        data={"caption": caption},
    )


async def make_figure(c, **kw) -> dict:
    r = await upload(c, kw.pop("data", make_png()), **kw)
    assert r.status_code == 201, r.text
    return r.json()


async def attach(c, question_id, **body):
    return await c.patch(f"/questions/{question_id}", json=body)


# --- upload ----------------------------------------------------------------


async def test_upload_png_returns_metadata_and_a_url(admin_client):
    r = await upload(admin_client, make_png(size=(400, 300)), caption="  A  leaf   cell ")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mime"] == "image/png"
    assert (body["width"], body["height"]) == (400, 300)
    assert body["caption"] == "A leaf cell"  # whitespace tidied
    assert body["size_bytes"] > 0
    assert body["url"].endswith(f"/figures/{body['id']}/file")


async def test_jpeg_stays_jpeg_and_exif_metadata_is_stripped(admin_client):
    fig = await make_figure(admin_client, data=make_jpeg(exif=True), name="p.jpg", ctype="image/jpeg")
    assert fig["mime"] == "image/jpeg"
    raw = await admin_client.get(f"/figures/{fig['id']}/file")
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "image/jpeg"
    stored = Image.open(BytesIO(raw.content))
    assert 0x010F not in stored.getexif()


async def test_transparency_is_flattened_onto_white(admin_client):
    clear = make_png(color=(0, 0, 0, 0), size=(40, 40), mode="RGBA")
    fig = await make_figure(admin_client, data=clear)
    raw = await admin_client.get(f"/figures/{fig['id']}/file")
    stored = Image.open(BytesIO(raw.content))
    assert stored.mode == "RGB"
    assert stored.getpixel((39, 0)) == (255, 255, 255)  # not black


async def test_very_large_images_are_scaled_down_for_print(admin_client):
    fig = await make_figure(admin_client, data=make_png(size=(3600, 1200)))
    assert fig["width"] == figure_service.MAX_SIDE_PX == 2400
    assert fig["height"] == 800


async def test_gif_is_converted_to_png(admin_client):
    buf = BytesIO()
    Image.new("P", (50, 50), 3).save(buf, "GIF")
    fig = await make_figure(admin_client, data=buf.getvalue(), name="a.gif", ctype="image/gif")
    assert fig["mime"] == "image/png"


@pytest.mark.parametrize(
    "payload,name",
    [
        (b"", "empty.png"),
        (b"just some text, not an image", "notes.png"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "x.svg"),
        (b"%PDF-1.4 fake", "doc.png"),
    ],
)
async def test_non_images_are_rejected(admin_client, payload, name):
    r = await upload(admin_client, payload, name=name)
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_image"


async def test_truncated_image_is_rejected(admin_client):
    r = await upload(admin_client, make_png()[:120])
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_image"


async def test_client_filename_and_content_type_are_ignored(admin_client):
    # A real PNG labelled as text, with a path-traversal name, is still stored
    # under a server-generated name.
    r = await upload(admin_client, make_png(), name="../../etc/passwd", ctype="text/plain")
    assert r.status_code == 201, r.text
    stored = [p.name for p in figure_service.figure_dir().iterdir()]
    assert f"{r.json()['id']}.png" in stored


async def test_oversized_upload_is_413(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "max_figure_bytes", 2048)
    r = await upload(admin_client, make_png(size=(600, 600)))
    assert r.status_code == 413, r.text
    assert r.json()["error"] == "payload_too_large"


async def test_pixel_bomb_is_rejected_before_decoding(admin_client, monkeypatch):
    monkeypatch.setattr(figure_service, "MAX_PIXELS", 1000)
    r = await upload(admin_client, make_png(size=(100, 100)))
    assert r.status_code == 400
    assert "too large" in r.json()["detail"]


async def test_caption_length_is_limited(admin_client):
    r = await upload(admin_client, make_png(), caption="x" * 301)
    assert r.status_code == 400


# --- reading, listing, caption, delete ---------------------------------------


async def test_delete_removes_the_row_and_the_file(admin_client):
    fig = await make_figure(admin_client)
    path = figure_service.figure_dir() / f"{fig['id']}.png"
    assert path.is_file()
    assert (await admin_client.delete(f"/figures/{fig['id']}")).status_code == 204
    assert not path.exists()
    assert (await admin_client.get(f"/figures/{fig['id']}")).status_code == 404


async def test_a_figure_in_use_cannot_be_deleted(client, admin_client):
    fig = await make_figure(admin_client)
    q = (await generate_questions(client, count=1))[0]
    assert (await attach(client, q["id"], figure_id=fig["id"])).status_code == 200

    r = await admin_client.delete(f"/figures/{fig['id']}")
    assert r.status_code == 409
    assert r.json()["error"] == "figure_in_use"

    # Detach, and now it can go.
    assert (await attach(client, q["id"], figure_id=None)).status_code == 200
    assert (await admin_client.delete(f"/figures/{fig['id']}")).status_code == 204


async def test_everyone_signed_in_sees_the_whole_library(admin_client, client, bob_client):
    first = await make_figure(admin_client, caption="first")
    second = await make_figure(admin_client, caption="second")
    for c in (admin_client, client, bob_client):
        listing = (await c.get("/figures")).json()
        assert listing["total"] == 2
        assert {f["id"] for f in listing["results"]} == {first["id"], second["id"]}


async def test_anyone_signed_in_can_read_a_figure_but_anonymous_cannot(admin_client, client, anon_client):
    fig = await make_figure(admin_client)
    assert (await client.get(f"/figures/{fig['id']}")).status_code == 200
    assert (await client.get(f"/figures/{fig['id']}/file")).status_code == 200
    assert (await anon_client.get(f"/figures/{fig['id']}/file")).status_code == 401
    assert (await anon_client.get("/figures")).status_code == 401
    assert (await client.get(f"/figures/{uuid.uuid4()}")).status_code == 404


async def test_admin_can_edit_and_delete_any_figure_from_the_library(admin_client, session_factory):
    """A second administrator manages figures the first one uploaded."""
    from sqlalchemy import update
    from httpx import ASGITransport, AsyncClient
    from app.main import app as fastapi_app
    from app.models import User
    from .conftest import sign_up

    fig = await make_figure(admin_client, caption="old")
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as other:
        await sign_up(other, name="Second Admin", email="admin2@school.test")
        async with session_factory() as session:
            await session.execute(update(User).where(User.email == "admin2@school.test").values(role="Admin"))
            await session.commit()
        ok = await other.patch(f"/figures/{fig['id']}", json={"caption": "new"})
        assert ok.status_code == 200 and ok.json()["caption"] == "new"
        assert (await other.delete(f"/figures/{fig['id']}")).status_code == 204



# --- attaching to questions --------------------------------------------------


async def test_attach_and_detach_figures_on_a_question(client, admin_client):
    fig = await make_figure(admin_client, caption="Leaf cross-section")
    key = await make_figure(admin_client, caption="Labelled leaf")
    q = (await generate_questions(client, count=1))[0]
    assert "figure" not in q and "answer_figure" not in q  # contract unchanged

    r = await attach(client, q["id"], figure_id=fig["id"], answer_figure_id=key["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["figure"]["id"] == fig["id"]
    assert body["figure"]["caption"] == "Leaf cross-section"
    assert body["answer_figure"]["id"] == key["id"]
    assert body["text"] == q["text"]  # nothing else changed

    again = (await client.get(f"/questions/{q['id']}")).json()
    assert again["figure"]["id"] == fig["id"]

    # Detach only the question figure; the key figure stays.
    r = await attach(client, q["id"], figure_id=None)
    assert "figure" not in r.json()
    assert r.json()["answer_figure"]["id"] == key["id"]


async def test_attaching_works_together_with_a_text_edit(client, admin_client):
    fig = await make_figure(admin_client)
    q = (await generate_questions(client, count=1, marks=3))[0]
    r = await attach(client, q["id"], figure_id=fig["id"], topic="cells")
    assert r.status_code == 200
    assert r.json()["topic"] == "cells" and r.json()["figure"]["id"] == fig["id"]


async def test_figure_is_part_of_a_questions_identity():
    chapter = uuid.uuid4()
    plain = content_hash("Science", chapter, "Label the diagram.")
    assert plain == content_hash("Science", chapter, "Label the diagram.", None)
    a = content_hash("Science", chapter, "Label the diagram.", uuid.uuid4())
    b = content_hash("Science", chapter, "Label the diagram.", uuid.uuid4())
    assert len({plain, a, b}) == 3


# --- practice mode: the key figure must not leak ------------------------------


async def test_practice_hides_the_answer_figure_until_reveal(client, admin_client, practice_shortfall_on):
    fig = await make_figure(admin_client, caption="Question figure")
    key = await make_figure(admin_client, caption="Answer figure")
    session = (
        await client.post(
            "/practice/sessions",
            json={"subject": "Science", "chapter": "Photosynthesis", "type": "MCQ",
                  "grade": 8, "difficulty": "easy", "count": 2},
        )
    ).json()
    qid = session["questions"][0]["id"]
    assert (await attach(client, qid, figure_id=fig["id"], answer_figure_id=key["id"])).status_code == 200

    shown = (await client.get(f"/practice/sessions/{session['id']}")).json()
    first = next(q for q in shown["questions"] if q["id"] == qid)
    assert first["figure"]["id"] == fig["id"]
    assert "answer_figure" not in first
    assert key["id"] not in str(shown)

    revealed = (await client.get(f"/practice/sessions/{session['id']}/reveal/{qid}")).json()
    assert revealed["answer_figure"]["id"] == key["id"]


async def test_any_teacher_can_attach_a_library_figure(admin_client, client):
    fig = await make_figure(admin_client, caption="Shared diagram")
    q = (await generate_questions(client, count=1))[0]
    r = await attach(client, q["id"], figure_id=fig["id"])
    assert r.status_code == 200 and r.json()["figure"]["id"] == fig["id"]


async def test_cannot_attach_a_missing_figure(client):
    q = (await generate_questions(client, count=1))[0]
    assert (await attach(client, q["id"], answer_figure_id=str(uuid.uuid4()))).status_code == 404
    assert "figure" not in (await client.get(f"/questions/{q['id']}")).json()


async def test_cannot_attach_to_a_question_you_did_not_generate(admin_client, client, bob_client):
    fig = await make_figure(admin_client)
    q = (await generate_questions(client, count=1))[0]
    assert (await attach(bob_client, q["id"], figure_id=fig["id"])).status_code == 403



# --- printing ----------------------------------------------------------------


async def _paper_with_figures(client, admin_client, db_session, n=1, *, marks=3, type="Short",
                              with_question_fig=True, with_answer_fig=True):
    """A paper of n questions, each with its own distinct figure(s)."""
    qs = await generate_questions(client, count=n, marks=marks, type=type)
    for i, q in enumerate(qs):
        body = {}
        if with_question_fig:
            body["figure_id"] = (await make_figure(
                admin_client, data=make_png(color=(10 + i * 20, 90, 200 - i * 10), size=(420, 280)),
                caption=f"Question figure {i + 1}"))["id"]
        if with_answer_fig:
            body["answer_figure_id"] = (await make_figure(
                admin_client, data=make_png(color=(200 - i * 15, 160, 30 + i * 10), size=(300, 300)),
                caption=f"Answer figure {i + 1}"))["id"]
        if body:
            assert (await attach(client, q["id"], **body)).status_code == 200
    r = await client.post(
        "/papers",
        json={"title": "Figure Paper", "subject": "Science", "question_ids": [q["id"] for q in qs]},
    )
    assert r.status_code == 201, r.text
    stmt = (
        select(Paper)
        .where(Paper.id == uuid.UUID(r.json()["id"]))
        .execution_options(populate_existing=True)
    )
    return (await db_session.execute(stmt)).unique().scalar_one()


def _images_per_page(pdf: bytes) -> list[int]:
    """How many images each page actually *draws*.

    Counts `Do` operators that paint an image XObject, rather than the images in
    the page's resource dictionary: WeasyPrint shares one resource dictionary
    across pages, so `page.images` would list every image on every page.
    """
    from pypdf.generic import ContentStream

    reader = PdfReader(BytesIO(pdf))
    counts = []
    for page in reader.pages:
        xobjects = (page.get("/Resources") or {}).get("/XObject") or {}
        n = 0
        for operands, operator in ContentStream(page.get_contents(), reader).operations:
            if operator == b"Do" and operands:
                xo = xobjects.get(operands[0])
                if xo is not None and xo.get_object().get("/Subtype") == "/Image":
                    n += 1
        counts.append(n)
    return counts


async def test_html_prints_the_question_figure_and_the_answer_figure(client, admin_client, db_session):
    paper = await _paper_with_figures(client, admin_client, db_session, n=1)
    out = html_service.render_paper_html(paper)
    key_at = out.index("Answer Key")
    paper_part, key_part = out[:key_at], out[key_at:]

    assert paper_part.count("data:image/png;base64,") == 1
    assert "Question figure 1" in paper_part and "Answer figure 1" not in paper_part
    assert key_part.count("data:image/png;base64,") == 1
    assert "Answer figure 1" in key_part

    no_key = html_service.render_paper_html(paper, include_answer_key=False)
    assert no_key.count("data:image/png;base64,") == 1  # the key figure is not printed


async def test_html_without_figures_is_unchanged(client, admin_client, db_session):
    paper = await _paper_with_figures(
        client, admin_client, db_session, n=2, with_question_fig=False, with_answer_fig=False
    )
    assert "<img" not in html_service.render_paper_html(paper)


async def test_answer_figure_earns_the_diagram_mark(client, admin_client, db_session):
    paper = await _paper_with_figures(client, admin_client, db_session, n=1, marks=3, with_question_fig=False)
    assert "Marks split: Diagram - 1, Explanation - 2" in html_service.render_paper_html(paper)


async def test_no_answer_figure_means_no_diagram_mark(client, admin_client, db_session):
    paper = await _paper_with_figures(
        client, admin_client, db_session, n=1, marks=3, with_question_fig=False, with_answer_fig=False
    )
    assert "Diagram -" not in html_service.render_paper_html(paper)


async def test_mcq_answer_figure_is_printed_in_the_key(client, admin_client, db_session):
    paper = await _paper_with_figures(
        client, admin_client, db_session, n=1, marks=1, type="MCQ", with_question_fig=False
    )
    out = html_service.render_paper_html(paper)
    assert out[out.index("Answer Key"):].count("<img") == 1


@pytest.mark.parametrize("backend", ["reportlab", "fpdf"])
async def test_pdf_contains_both_figures(client, admin_client, db_session, monkeypatch, backend):
    if backend == "fpdf" and not renderer_service.fpdf_available():
        pytest.skip("fpdf2 + uharfbuzz not installed")
    monkeypatch.setattr(settings, "pdf_renderer", backend)
    paper = await _paper_with_figures(client, admin_client, db_session, n=1)

    pdf = renderer_service.render_pdf(paper)
    assert pdf.startswith(b"%PDF")
    per_page = _images_per_page(pdf)
    # Page 1 carries the question's figure; the answer key (a new page) its own.
    assert per_page == [1, 1], per_page


@pytest.mark.parametrize("backend", ["reportlab", "fpdf"])
async def test_many_figures_across_page_breaks_all_survive(client, admin_client, db_session, monkeypatch, backend):
    if backend == "fpdf" and not renderer_service.fpdf_available():
        pytest.skip("fpdf2 + uharfbuzz not installed")
    monkeypatch.setattr(settings, "pdf_renderer", backend)
    n = 9
    paper = await _paper_with_figures(client, admin_client, db_session, n=n)

    per_page = _images_per_page(renderer_service.render_pdf(paper))
    assert sum(per_page) == 2 * n, per_page
    assert len(per_page) >= 3  # it really did span several pages


@pytest.mark.parametrize("backend", ["reportlab", "fpdf"])
async def test_a_missing_image_file_does_not_break_the_export(client, admin_client, db_session, monkeypatch, backend):
    if backend == "fpdf" and not renderer_service.fpdf_available():
        pytest.skip("fpdf2 + uharfbuzz not installed")
    monkeypatch.setattr(settings, "pdf_renderer", backend)
    paper = await _paper_with_figures(client, admin_client, db_session, n=1)
    for f in figure_service.figure_dir().glob("*.png"):
        f.unlink()

    pdf = renderer_service.render_pdf(paper)
    assert pdf.startswith(b"%PDF")
    assert sum(_images_per_page(pdf)) == 0


@pytest.mark.skipif(not renderer_service.weasyprint_available(), reason="WeasyPrint not installed")
async def test_weasyprint_pdf_contains_both_figures(client, admin_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "pdf_renderer", "weasyprint")
    paper = await _paper_with_figures(client, admin_client, db_session, n=1)
    assert sum(_images_per_page(renderer_service.render_pdf(paper))) == 2


async def test_export_endpoint_produces_a_pdf_with_the_figures(client, admin_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "pdf_renderer", "reportlab")
    paper = await _paper_with_figures(client, admin_client, db_session, n=1)
    r = await client.post(f"/export/{paper.id}")
    assert r.status_code == 200, r.text
    from app.services.export import export_dir

    pdf = (export_dir() / r.json()["filename"]).read_bytes()
    assert sum(_images_per_page(pdf)) == 2


async def test_paper_endpoint_carries_the_figures(client, admin_client, db_session):
    paper = await _paper_with_figures(client, admin_client, db_session, n=1)
    body = (await client.get(f"/papers/{paper.id}")).json()
    q = body["questions"][0]["question"]
    assert q["figure"]["caption"] == "Question figure 1"
    assert q["answer_figure"]["caption"] == "Answer figure 1"


# --- layout helper -----------------------------------------------------------


async def test_fit_size_never_exceeds_the_print_box_and_keeps_aspect():
    w, h = figure_service.fit_size_mm(2400, 800)
    assert w <= figure_service.MAX_FIGURE_WIDTH_MM and h <= figure_service.MAX_FIGURE_HEIGHT_MM
    assert abs(w / h - 3.0) < 0.02
    tall_w, tall_h = figure_service.fit_size_mm(500, 2400)
    assert tall_h <= figure_service.MAX_FIGURE_HEIGHT_MM
    # A small image is not stretched up to fill the width.
    small_w, _ = figure_service.fit_size_mm(150, 100)
    assert small_w == pytest.approx(25.4, abs=0.1)


# --- answer key falls back to the question's own figure ---------------------


async def test_answer_key_shows_the_question_figure_when_there_is_no_answer_figure(
    client, admin_client, db_session
):
    """Generated questions are saved with `figure` only; the key must still show it."""
    paper = await _paper_with_figures(client, admin_client, db_session, n=1, with_answer_fig=False)
    out = html_service.render_paper_html(paper)
    paper_part, key_part = out[: out.index("Answer Key")], out[out.index("Answer Key"):]
    assert paper_part.count("<img") == 1
    assert key_part.count("<img") == 1
    assert "Question figure 1" in key_part


async def test_explicit_answer_figure_wins_over_the_question_figure_in_the_key(
    client, admin_client, db_session
):
    paper = await _paper_with_figures(client, admin_client, db_session, n=1)
    key_part = html_service.render_paper_html(paper)
    key_part = key_part[key_part.index("Answer Key"):]
    assert "Answer figure 1" in key_part and "Question figure 1" not in key_part


@pytest.mark.parametrize("backend", ["reportlab", "fpdf"])
async def test_pdf_answer_key_repeats_the_question_figure(
    client, admin_client, db_session, monkeypatch, backend
):
    if backend == "fpdf" and not renderer_service.fpdf_available():
        pytest.skip("fpdf2 + uharfbuzz not installed")
    monkeypatch.setattr(settings, "pdf_renderer", backend)
    paper = await _paper_with_figures(client, admin_client, db_session, n=1, with_answer_fig=False)
    pdf = renderer_service.render_pdf(paper)
    assert sum(_images_per_page(pdf)) == 2  # once in the paper, once in the key


# --- uploads are backend-only ----------------------------------------------


# --- only administrators change the library ------------------------------------


async def test_only_admins_can_upload_edit_or_delete_figures(admin_client, client, bob_client):
    fig = await make_figure(admin_client, caption="old")
    files = {"file": ("fig.png", make_png(), "image/png")}
    for teacher in (client, bob_client):
        r = await teacher.post("/figures", files={"file": ("fig.png", make_png(), "image/png")})
        assert r.status_code == 403 and r.json()["error"] == "admin_required"
        r = await teacher.patch(f"/figures/{fig['id']}", json={"caption": "x"})
        assert r.status_code == 403 and r.json()["error"] == "admin_required"
        r = await teacher.delete(f"/figures/{fig['id']}")
        assert r.status_code == 403 and r.json()["error"] == "admin_required"
    # Nothing changed, and reading is unaffected.
    shown = (await client.get(f"/figures/{fig['id']}")).json()
    assert shown["caption"] == "old"
    assert (await client.get("/figures")).json()["total"] == 1
    assert files  # silence unused warning


async def test_a_denied_upload_stores_nothing(client):
    before = len(list(figure_service.figure_dir().iterdir()))
    r = await client.post("/figures", files={"file": ("f.png", make_png(), "image/png")})
    assert r.status_code == 403
    assert len(list(figure_service.figure_dir().iterdir())) == before
    assert (await client.get("/figures")).json()["total"] == 0


async def test_you_cannot_make_yourself_an_admin(client):
    me = (await client.get("/auth/me")).json()
    assert me["role"] == "Teacher"
    r = await client.patch("/auth/me", json={"role": "Admin"})
    assert r.status_code == 400  # not an accepted value
    assert (await client.get("/auth/me")).json()["role"] == "Teacher"
    r = await client.post(
        "/auth/signup",
        json={"name": "Sneaky", "email": "sneaky@school.test", "password": "Passw0rd-test", "role": "Admin"},
    )
    assert r.status_code == 400


async def test_a_role_change_by_the_database_takes_effect_on_the_next_request(admin_client, client, session_factory):
    """The role is read from the account on every request, not baked into the token."""
    from sqlalchemy import update
    from app.models import User

    assert (await client.post("/figures", files={"file": ("f.png", make_png(), "image/png")})).status_code == 403
    async with session_factory() as session:
        await session.execute(update(User).where(User.email == "alice@school.test").values(role="Admin"))
        await session.commit()
    assert (await client.post("/figures", files={"file": ("f.png", make_png(), "image/png")})).status_code == 201
    async with session_factory() as session:
        await session.execute(update(User).where(User.email == "alice@school.test").values(role="Teacher"))
        await session.commit()
    assert (await client.post("/figures", files={"file": ("f.png", make_png(), "image/png")})).status_code == 403
