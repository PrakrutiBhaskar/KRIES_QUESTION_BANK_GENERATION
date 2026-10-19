"""Seeding a new syllabus from the app: teachers and administrators only, live without a restart."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from app.models import SeededChapter
from app.services import generation as generation_service
from app.services import syllabus as syllabus_service

pytestmark = pytest.mark.asyncio

BODY = {
    "subject": "Science",
    "grade": 8,
    "chapters": [
        {"name": "Crop Production", "topics": ["Kharif crops", "Rabi crops"]},
        {"name": "Microorganisms"},
    ],
}


@pytest.fixture(autouse=True)
def _restore_syllabus_globals():
    """Seeding rebuilds the process-wide syllabus; put it back after each test."""
    saved = (
        syllabus_service._syllabus_index,
        syllabus_service._grade_chapters,
        syllabus_service._base_dict,
    )
    yield
    (
        syllabus_service._syllabus_index,
        syllabus_service._grade_chapters,
        syllabus_service._base_dict,
    ) = saved


@pytest.fixture
async def student(client):
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        r = await c.post(
            "/auth/signup",
            json={"name": "Stu Dent", "email": "stu2@school.test", "password": "Passw0rd-test", "role": "Student"},
        )
        assert r.status_code == 201, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        yield c


async def test_a_teacher_can_seed_chapters_and_they_are_offered_at_once(client):
    r = await client.post("/syllabus/seed", json=BODY)
    assert r.status_code == 201, r.text
    out = r.json()
    assert [c["name"] for c in out["added"]] == ["Crop Production", "Microorganisms"]
    assert out["added"][0]["topics"] == ["Kharif crops", "Rabi crops"]
    assert out["skipped"] == []

    chapters = (await client.get("/subjects/Science/chapters", params={"grade": 8})).json()
    assert {c["name"] for c in chapters} >= {"Crop Production", "Microorganisms"}
    # ...and only for the grade they were seeded under
    other = (await client.get("/subjects/Science/chapters", params={"grade": 7})).json()
    assert "Crop Production" not in {c["name"] for c in other}


async def test_the_engine_uses_the_new_syllabus(client):
    await client.post("/syllabus/seed", json=BODY)
    index = syllabus_service.get_syllabus_index()
    assert index.has_chapter(syllabus_service.SubjectEnum.SCIENCE, "crop production", grade=8)
    assert index.topics(syllabus_service.SubjectEnum.SCIENCE, "Crop Production") == ["Kharif crops", "Rabi crops"]
    engine = generation_service._engine
    if engine is not None:
        assert engine.syllabus is index


async def test_chapters_already_in_the_grade_are_skipped(client):
    await client.post("/syllabus/seed", json=BODY)
    again = await client.post(
        "/syllabus/seed",
        json={"subject": "Science", "grade": 8, "chapters": [{"name": " crop  production "}, {"name": "Light"}, {"name": "Light"}]},
    )
    assert again.status_code == 201
    assert [c["name"] for c in again.json()["added"]] == ["Light"]
    assert again.json()["skipped"] == ["crop production", "Light"]


async def test_the_same_chapter_can_be_seeded_for_another_grade(client):
    await client.post("/syllabus/seed", json=BODY)
    r = await client.post(
        "/syllabus/seed",
        json={"subject": "Science", "grade": 9, "chapters": [{"name": "Crop Production"}]},
    )
    assert [c["name"] for c in r.json()["added"]] == ["Crop Production"]


async def test_bad_requests_are_refused(client):
    for body in (
        {"subject": "Science", "grade": 6, "chapters": [{"name": "X"}]},
        {"subject": "Science", "grade": 10, "chapters": [{"name": "X"}]},
        {"subject": "Astrology", "grade": 8, "chapters": [{"name": "X"}]},
        {"subject": "Science", "grade": 8, "chapters": []},
        {"subject": "Science", "grade": 8, "chapters": [{"name": "   "}]},
    ):
        r = await client.post("/syllabus/seed", json=body)
        assert r.status_code in (400, 422), (body, r.status_code)


async def test_seeded_chapters_survive_a_reload(client, db_session):
    await client.post("/syllabus/seed", json=BODY)
    syllabus_service._syllabus_index = None  # as after a restart
    index = await syllabus_service.reload_seeded(db_session)
    assert index.has_chapter(syllabus_service.SubjectEnum.SCIENCE, "Microorganisms", grade=8)


async def test_the_list_shows_who_can_remove_what(client, bob_client, admin_client):
    await client.post("/syllabus/seed", json=BODY)
    mine = (await client.get("/syllabus/seeded", params={"subject": "Science", "grade": 8})).json()
    assert len(mine) == 2 and all(c["can_remove"] for c in mine)
    bobs = (await bob_client.get("/syllabus/seeded")).json()
    assert len(bobs) == 2 and not any(c["can_remove"] for c in bobs)
    assert all(c["can_remove"] for c in (await admin_client.get("/syllabus/seeded")).json())


async def test_only_the_creator_or_an_admin_can_remove_a_seeded_chapter(client, bob_client, admin_client):
    # With a base syllabus loaded (as in a real deployment), a removed chapter stops being offered.
    syllabus_service._base_dict = {"Math": {"chapters": ["Rational Numbers"], "grades": {"8": ["Rational Numbers"]}}}
    await client.post("/syllabus/seed", json=BODY)
    first, second = (await client.get("/syllabus/seeded")).json()

    assert (await bob_client.delete(f"/syllabus/seeded/{first['id']}")).status_code == 403
    assert (await client.delete(f"/syllabus/seeded/{first['id']}")).status_code == 204
    assert (await admin_client.delete(f"/syllabus/seeded/{second['id']}")).status_code == 204
    assert (await client.delete(f"/syllabus/seeded/{second['id']}")).status_code == 404

    names = {c["name"] for c in (await client.get("/subjects/Science/chapters", params={"grade": 8})).json()}
    assert not names & {"Crop Production", "Microorganisms"}


async def test_a_student_cannot_see_seed_or_remove(client, student):
    await client.post("/syllabus/seed", json=BODY)
    row = (await client.get("/syllabus/seeded")).json()[0]
    for call in (
        student.post("/syllabus/seed", json=BODY),
        student.get("/syllabus/seeded"),
        student.delete(f"/syllabus/seeded/{row['id']}"),
    ):
        r = await call
        assert r.status_code == 403, r.text
        assert r.json()["error"] == "editor_required"
    # the student still sees the syllabus itself
    assert (await student.get("/subjects/Science/chapters", params={"grade": 8})).status_code == 200


async def test_an_unauthenticated_caller_is_refused(anon_client):
    assert (await anon_client.post("/syllabus/seed", json=BODY)).status_code == 401


def test_merge_keeps_the_textbook_syllabus_and_adds_the_seeded_chapters():
    base = {"Science": {"chapters": ["Light"], "grades": {"8": ["Light"]}, "topics": {"Light": ["Mirrors"]}}}
    rows = [SeededChapter(subject="Science", grade=8, name="Crop Production", name_key="crop production", topics=["Kharif"])]
    merged = syllabus_service.merge_seeded(base, rows)
    assert merged["Science"]["grades"]["8"] == ["Light", "Crop Production"]
    assert merged["Science"]["topics"] == {"Light": ["Mirrors"], "Crop Production": ["Kharif"]}
    assert base["Science"]["grades"]["8"] == ["Light"]  # the base is not mutated
