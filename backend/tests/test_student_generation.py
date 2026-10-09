"""Students can generate question banks and papers, database first, with a capped allowance.

  * Stored questions are always used before the model is asked for anything;
    only the shortfall reaches the API.
  * A student cannot force fresh generation (`refresh` is ignored).
  * New questions a student may create are capped per request and per day.
  * Teachers and administrators are not capped.
  * Answer verification (an AI pass with no stored-question path) stays teacher-only.
  * Practice mode still never calls the model by default.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app as fastapi_app

from .test_blueprint import _wait_for_job, blueprint
from .test_rate_limiting import GENERATE

pytestmark = pytest.mark.asyncio

PRACTICE = {"subject": "Science", "chapter": "Photosynthesis", "type": "MCQ", "grade": 8, "count": 2}
SHORT = {**GENERATE, "type": "Short", "marks": 2, "difficulty": "medium"}


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


@pytest.fixture
def allowance(monkeypatch):
    def set_(*, per_request: int = 10, per_day: int = 30) -> None:
        monkeypatch.setattr(settings, "student_max_new_per_request", per_request)
        monkeypatch.setattr(settings, "student_max_new_per_day", per_day)

    return set_


# --- /generate: database first ------------------------------------------------


async def test_a_student_can_generate_when_the_bank_is_empty(student, groq_stub):
    r = await student.post("/generate", json={**SHORT, "count": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["cached"], body["generated"], len(body["questions"])) == (0, 3, 3)
    assert len(groq_stub.generation_calls) == 1


async def test_stored_questions_are_served_without_calling_the_api(client, student, groq_stub):
    assert (await client.post("/generate", json={**SHORT, "count": 5})).status_code == 200
    calls = len(groq_stub.generation_calls)

    r = await student.post("/generate", json={**SHORT, "count": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["cached"], body["generated"]) == (5, 0)
    assert len(groq_stub.generation_calls) == calls  # the model was never asked


async def test_only_the_shortfall_is_generated(client, student, groq_stub):
    assert (await client.post("/generate", json={**SHORT, "count": 2})).status_code == 200
    calls = len(groq_stub.generation_calls)

    r = await student.post("/generate", json={**SHORT, "count": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["cached"], body["generated"], len(body["questions"])) == (2, 3, 5)
    assert len(groq_stub.generation_calls) == calls + 1


async def test_a_student_cannot_force_fresh_generation(client, student, groq_stub):
    assert (await client.post("/generate", json={**SHORT, "count": 3})).status_code == 200
    calls = len(groq_stub.generation_calls)

    r = await student.post("/generate", json={**SHORT, "count": 3, "refresh": True})
    assert r.status_code == 200, r.text
    assert (r.json()["cached"], r.json()["generated"]) == (3, 0)
    assert len(groq_stub.generation_calls) == calls


async def test_a_teacher_can_still_refresh(client, groq_stub):
    assert (await client.post("/generate", json={**SHORT, "count": 3})).status_code == 200
    r = await client.post("/generate", json={**SHORT, "count": 3, "refresh": True})
    assert r.status_code == 200
    assert r.json()["generated"] == 3


# --- /generate: the allowance -------------------------------------------------


async def test_a_request_needing_too_many_new_questions_is_refused(student, groq_stub, allowance):
    allowance(per_request=2)
    r = await student.post("/generate", json={**SHORT, "count": 3})
    assert r.status_code == 429
    assert r.json()["error"] == "generation_allowance_used"
    assert len(groq_stub.generation_calls) == 0  # refused before spending anything
    assert (await student.get("/questions")).json()["total"] == 0


async def test_the_cap_only_counts_new_questions_not_stored_ones(client, student, allowance):
    assert (await client.post("/generate", json={**SHORT, "count": 5})).status_code == 200
    allowance(per_request=2)
    r = await student.post("/generate", json={**SHORT, "count": 5})
    assert r.status_code == 200, r.text
    assert r.json()["generated"] == 0


async def test_the_daily_allowance_runs_out(student, groq_stub, allowance):
    allowance(per_request=10, per_day=3)
    assert (await student.post("/generate", json={**SHORT, "count": 3})).status_code == 200

    # A different difficulty is not in the bank, so it would need new questions.
    r = await student.post("/generate", json={**SHORT, "difficulty": "hard", "count": 1})
    assert r.status_code == 429
    assert r.json()["error"] == "generation_allowance_used"
    assert "today" in r.json()["detail"]
    assert len(groq_stub.generation_calls) == 1

    # Stored questions are still free once the allowance is gone.
    again = await student.post("/generate", json={**SHORT, "count": 3})
    assert again.status_code == 200 and again.json()["generated"] == 0


async def test_teachers_are_not_capped(client, allowance):
    allowance(per_request=1, per_day=1)
    r = await client.post("/generate", json={**SHORT, "count": 3})
    assert r.status_code == 200
    assert r.json()["generated"] == 3


async def test_an_allowance_of_zero_turns_student_generation_off(student, groq_stub, allowance):
    allowance(per_request=0)
    assert (await student.post("/generate", json={**SHORT, "count": 1})).status_code == 429
    assert len(groq_stub.generation_calls) == 0


# --- verification stays with teachers ----------------------------------------


async def test_a_student_cannot_verify_answers(student):
    r = await student.post("/questions/verify", json={"question_ids": []})
    assert r.status_code == 403
    assert r.json()["error"] == "generation_disabled_for_students"


async def test_a_teacher_can_still_verify(client):
    questions = (await client.post("/generate", json={**SHORT, "count": 1})).json()["questions"]
    r = await client.post("/questions/verify", json={"question_ids": [questions[0]["id"]]})
    assert r.status_code == 200


# --- papers ------------------------------------------------------------------


async def test_a_student_builds_a_paper_from_stored_questions(client, student, groq_stub):
    assert (await client.post("/papers/blueprint", json=blueprint())).status_code == 201
    calls = len(groq_stub.generation_calls)

    r = await student.post("/papers/blueprint", json=blueprint(refresh=True))
    assert r.status_code == 201, r.text
    assert len(r.json()["questions"]) == 17
    assert len(groq_stub.generation_calls) == calls  # all of it came from the bank
    # The paper is the student's own.
    assert len((await student.get("/papers")).json()) == 1


async def test_a_paper_needing_too_many_new_questions_stores_nothing(student, groq_stub):
    # Empty bank: 17 new questions would be needed, more than the default 10 per request.
    r = await student.post("/papers/blueprint", json=blueprint())
    assert r.status_code == 429
    assert r.json()["error"] == "generation_allowance_used"
    assert (await student.get("/papers")).json() == []
    assert (await student.get("/questions")).json()["total"] == 0
    # Refused up front: no model call was made, so nothing was wasted.
    assert len(groq_stub.generation_calls) == 0


async def test_a_small_paper_within_the_allowance_is_built(student, groq_stub):
    small = blueprint(
        chapters=[{"name": "Photosynthesis", "weightage": 100}],
        sections=[{"name": "A", "type": "MCQ", "marks_per_question": 1, "total_marks": 5}],
    )
    r = await student.post("/papers/blueprint", json=small)
    assert r.status_code == 201, r.text
    assert len(r.json()["questions"]) == 5


async def test_a_background_paper_build_uses_the_bank_for_students(client, student, groq_stub):
    assert (await client.post("/papers/blueprint", json=blueprint())).status_code == 201
    calls = len(groq_stub.generation_calls)

    started = await student.post("/papers/blueprint/jobs", json=blueprint())
    assert started.status_code == 202, started.text
    job, _ = await _wait_for_job(student, started.json()["id"])
    assert job["status"] == "done"
    assert len(groq_stub.generation_calls) == calls


async def test_a_background_build_over_the_allowance_reports_the_error(student, groq_stub):
    started = await student.post("/papers/blueprint/jobs", json=blueprint())
    assert started.status_code == 202, started.text
    job, _ = await _wait_for_job(student, started.json()["id"])
    assert job["status"] == "error"
    assert (job["error"], job["error_status"]) == ("generation_allowance_used", 429)
    assert len(groq_stub.generation_calls) == 0


# --- practice mode is unchanged ----------------------------------------------


async def test_practice_does_not_generate_by_default(client, student):
    # Empty bank + shortfall generation off => nothing is generated, so 422.
    r = await student.post("/practice/sessions", json=PRACTICE)
    assert r.status_code == 422


async def test_practice_serves_stored_questions_to_a_student(client, student):
    assert (await client.post("/generate", json={**GENERATE, "count": 2})).status_code == 200
    r = await student.post("/practice/sessions", json=PRACTICE)
    assert r.status_code == 201, r.text
