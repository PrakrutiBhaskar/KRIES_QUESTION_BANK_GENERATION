"""Student accounts can't trigger live generation (403), and practice never generates by default."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app

from .test_blueprint import blueprint
from .test_rate_limiting import GENERATE

PRACTICE = {"subject": "Science", "chapter": "Photosynthesis", "type": "MCQ", "grade": 8, "count": 2}


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


async def test_a_student_cannot_generate(student):
    r = await student.post("/generate", json=GENERATE)
    assert r.status_code == 403
    assert r.json()["error"] == "generation_disabled_for_students"


async def test_a_student_cannot_verify_or_build_blueprint_papers(student):
    assert (await student.post("/questions/verify", json={"question_ids": []})).status_code == 403
    assert (await student.post("/papers/blueprint", json=blueprint())).status_code == 403
    assert (await student.post("/papers/blueprint/jobs", json=blueprint())).status_code == 403


async def test_a_teacher_can_still_generate(client):
    assert (await client.post("/generate", json=GENERATE)).status_code == 200


async def test_practice_does_not_generate_by_default(client, student):
    # Empty bank + shortfall generation off => nothing is generated, so 422.
    r = await student.post("/practice/sessions", json=PRACTICE)
    assert r.status_code == 422


async def test_practice_serves_stored_questions_to_a_student(client, student):
    assert (await client.post("/generate", json={**GENERATE, "count": 2})).status_code == 200
    r = await student.post("/practice/sessions", json=PRACTICE)
    assert r.status_code == 201, r.text
