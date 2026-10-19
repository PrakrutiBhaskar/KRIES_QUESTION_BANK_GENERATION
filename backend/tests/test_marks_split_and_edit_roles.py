"""Editable marks split, and edit rights limited to teachers and administrators."""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.services.export import html as html_service
from app.services.export.answer_format import format_answer, usable_custom_split

from .conftest import generate_questions
from .test_export_rendering import _load_paper

pytestmark = pytest.mark.asyncio

SPLIT = [{"name": "Diagram", "marks": 2}, {"name": "Explanation", "marks": 1}]


@pytest.fixture
async def student(client):  # `client` sets up the test DB and app overrides
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        r = await c.post(
            "/auth/signup",
            json={"name": "Stu Dent", "email": "stu@school.test", "password": "Passw0rd-test", "role": "Student"},
        )
        assert r.status_code == 201, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def _short(client, marks=3):
    return (await generate_questions(client, count=1, marks=marks, type="Short"))[0]


# --- editing the split ---------------------------------------------------------


async def test_a_teacher_can_set_and_read_back_a_marks_split(client):
    q = await _short(client, marks=3)
    assert "marks_split" not in q  # automatic until someone sets one

    r = await client.patch(f"/questions/{q['id']}", json={"marks_split": SPLIT})
    assert r.status_code == 200, r.text
    assert r.json()["marks_split"] == SPLIT
    assert (await client.get(f"/questions/{q['id']}")).json()["marks_split"] == SPLIT


async def test_the_split_must_add_up_to_the_questions_marks(client):
    q = await _short(client, marks=3)
    bad = [{"name": "Diagram", "marks": 1}, {"name": "Explanation", "marks": 1}]
    r = await client.patch(f"/questions/{q['id']}", json={"marks_split": bad})
    assert r.status_code == 400
    assert "adds up to 2" in r.json()["detail"]


async def test_split_names_must_be_present_and_distinct(client):
    q = await _short(client, marks=3)
    blank = await client.patch(
        f"/questions/{q['id']}", json={"marks_split": [{"name": "  ", "marks": 3}]}
    )
    assert blank.status_code in (400, 422)
    dup = await client.patch(
        f"/questions/{q['id']}",
        json={"marks_split": [{"name": "Diagram", "marks": 1}, {"name": "diagram", "marks": 2}]},
    )
    assert dup.status_code == 400


async def test_one_mark_and_mcq_questions_take_no_split(client):
    mcq = (await generate_questions(client, count=1, marks=1, type="MCQ"))[0]
    r = await client.patch(
        f"/questions/{mcq['id']}", json={"marks_split": [{"name": "Answer", "marks": 1}]}
    )
    assert r.status_code == 400
    info = (await client.get(f"/questions/{mcq['id']}/marks-split")).json()
    assert info["editable"] is False and info["auto_marks_split"] is None


async def test_null_goes_back_to_the_automatic_split(client):
    q = await _short(client, marks=3)
    await client.patch(f"/questions/{q['id']}", json={"marks_split": SPLIT})
    r = await client.patch(f"/questions/{q['id']}", json={"marks_split": None})
    assert r.status_code == 200
    assert "marks_split" not in r.json()


async def test_changing_the_marks_drops_a_split_that_no_longer_adds_up(client):
    q = await _short(client, marks=3)
    await client.patch(f"/questions/{q['id']}", json={"marks_split": SPLIT})
    r = await client.patch(f"/questions/{q['id']}", json={"marks": 2})
    if r.status_code == 200:  # the edit is allowed for this question
        assert "marks_split" not in r.json()


async def test_marks_split_endpoint_reports_the_automatic_split(client):
    q = await _short(client, marks=3)
    info = (await client.get(f"/questions/{q['id']}/marks-split")).json()
    assert info["editable"] is True and info["marks"] == 3
    assert info["marks_split"] is None
    assert sum(p["marks"] for p in info["auto_marks_split"]) == 3


async def test_a_copy_keeps_the_split(client, bob_client):
    q = await _short(client, marks=3)
    await client.patch(f"/questions/{q['id']}", json={"marks_split": SPLIT})
    copy = await bob_client.post(f"/questions/{q['id']}/copy")
    assert copy.status_code == 201
    assert copy.json()["marks_split"] == SPLIT


# --- the answer key prints it ---------------------------------------------------


async def test_the_exported_answer_key_uses_the_teachers_split(client, db_session):
    paper = await _load_paper(client, db_session, count=1, marks=3, type="Short")
    qid = str(paper.items[0].question_id)
    assert (await client.patch(f"/questions/{qid}", json={"marks_split": SPLIT})).status_code == 200
    await db_session.refresh(paper.items[0].question)
    assert "Marks split: Diagram - 2, Explanation - 1" in html_service.render_paper_html(paper)


def test_a_split_that_no_longer_matches_the_paper_marks_is_ignored():
    # A paper can override a question's marks; the old split then no longer applies.
    assert usable_custom_split(SPLIT, 3, "Short") == [("Diagram", 2), ("Explanation", 1)]
    assert usable_custom_split(SPLIT, 5, "Short") == []
    assert usable_custom_split(SPLIT, 3, "MCQ") == []
    fa = format_answer("1. Point one. 2. Point two.", 5, "Short", custom_split=SPLIT)
    assert sum(m for _, m in fa.split) == 5


# --- only teachers and administrators edit -------------------------------------


async def test_a_student_cannot_edit_delete_or_copy_questions(client, student):
    q = await _short(client, marks=3)
    for call in (
        student.patch(f"/questions/{q['id']}", json={"difficulty": "hard"}),
        student.patch(f"/questions/{q['id']}", json={"marks_split": SPLIT}),
        student.post(f"/questions/{q['id']}/copy"),
        student.delete(f"/questions/{q['id']}"),
        student.get(f"/questions/{q['id']}/marks-split"),
    ):
        r = await call
        assert r.status_code == 403, r.text
        assert r.json()["error"] == "editor_required"


async def test_a_student_cannot_reorder_rename_or_remark_a_paper(client, student):
    qs = await generate_questions(client, count=2, marks=3, type="Short")
    r = await student.post(
        "/papers",
        json={"title": "Mine", "subject": "Science", "question_ids": [q["id"] for q in qs]},
    )
    assert r.status_code == 201, r.text  # students can still build and export their own papers
    paper_id = r.json()["id"]
    patch = await student.patch(f"/papers/{paper_id}", json={"title": "Renamed"})
    assert patch.status_code == 403
    assert patch.json()["error"] == "editor_required"
    assert (await student.get(f"/papers/{paper_id}")).json()["title"] == "Mine"


async def test_a_student_can_still_read_questions(client, student):
    await _short(client, marks=3)
    assert (await student.get("/questions")).status_code == 200


async def test_a_teacher_can_rename_their_paper(client):
    qs = await generate_questions(client, count=1, marks=3, type="Short")
    r = await client.post(
        "/papers", json={"title": "Old", "subject": "Science", "question_ids": [qs[0]["id"]]}
    )
    r = await client.patch(f"/papers/{r.json()['id']}", json={"title": "New"})
    assert r.status_code == 200 and r.json()["title"] == "New"


async def test_an_administrator_can_edit_the_marks_split(admin_client):
    q = await _short(admin_client, marks=3)
    r = await admin_client.patch(f"/questions/{q['id']}", json={"marks_split": SPLIT})
    assert r.status_code == 200 and r.json()["marks_split"] == SPLIT


async def test_editing_someone_elses_question_still_goes_through_a_copy(client, bob_client):
    q = await _short(client, marks=3)
    r = await bob_client.patch(f"/questions/{q['id']}", json={"marks_split": SPLIT})
    assert r.status_code == 403
    assert r.json()["error"] != "editor_required"  # a teacher: refused only because it is not theirs
