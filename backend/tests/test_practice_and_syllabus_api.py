"""
Practice mode and syllabus endpoints — test-plan.md Section 2, rows for
`POST /practice/sessions` and the reveal endpoint, plus Section 6 of the API
contract.
"""
from __future__ import annotations

import uuid

import pytest

from .conftest import generate_questions

pytestmark = pytest.mark.asyncio

SESSION = {
    "subject": "Science",
    "chapter": "Photosynthesis",
    "type": "MCQ",
    "grade": 8,
    "difficulty": "easy",
    "count": 4,
}


# --- session creation ------------------------------------------------------


async def test_session_draws_from_the_stored_bank(client, groq_stub):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=6)
    calls_before = len(groq_stub.calls)

    response = await client.post("/practice/sessions", json=SESSION)
    assert response.status_code == 201, response.text

    body = response.json()
    assert len(body["questions"]) == 4
    # The bank already had enough, so nothing was generated.
    assert len(groq_stub.calls) == calls_before


async def test_session_generates_when_the_bank_is_thin(client):
    response = await client.post("/practice/sessions", json=SESSION)
    assert response.status_code == 201
    assert len(response.json()["questions"]) == 4


async def test_answers_are_withheld_until_reveal(client):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=5)
    session = (await client.post("/practice/sessions", json=SESSION)).json()

    for question in session["questions"]:
        assert "answer" not in question
        assert "explanation" not in question
        assert question["revealed"] is False
        # Options still come through — the student needs them to attempt it.
        assert len(question["options"]) == 4


async def test_reveal_returns_the_answer_for_that_question(client):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=5)
    session = (await client.post("/practice/sessions", json=SESSION)).json()
    target = session["questions"][0]

    response = await client.get(
        f"/practice/sessions/{session['id']}/reveal/{target['id']}"
    )
    assert response.status_code == 200

    body = response.json()
    assert body["question_id"] == target["id"]
    assert body["answer"]

    # Cross-check against the canonical record.
    canonical = (await client.get(f"/questions/{target['id']}")).json()
    assert body["answer"] == canonical["answer"]
    assert body["explanation"] == canonical["explanation"]


async def test_reveal_does_not_leak_other_answers(client):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=5)
    session = (await client.post("/practice/sessions", json=SESSION)).json()
    target = session["questions"][0]

    revealed = (
        await client.get(f"/practice/sessions/{session['id']}/reveal/{target['id']}")
    ).json()
    assert set(revealed) == {"question_id", "answer", "explanation"}

    # The rest of the set stays masked on reload.
    resumed = (await client.get(f"/practice/sessions/{session['id']}")).json()
    revealed_flags = {q["id"]: q["revealed"] for q in resumed["questions"]}
    assert revealed_flags[target["id"]] is True
    assert all(
        flag is False for qid, flag in revealed_flags.items() if qid != target["id"]
    )
    assert all("answer" not in q for q in resumed["questions"])


async def test_reveal_rejects_a_question_outside_the_session(client):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=2)
    session = (await client.post("/practice/sessions", json={**SESSION, "count": 1})).json()

    outsider = (
        await generate_questions(
            client, type="MCQ", marks=1, difficulty="hard", count=1
        )
    )[0]

    response = await client.get(
        f"/practice/sessions/{session['id']}/reveal/{outsider['id']}"
    )
    assert response.status_code == 404


async def test_reveal_on_unknown_session_returns_404(client):
    response = await client.get(
        f"/practice/sessions/{uuid.uuid4()}/reveal/{uuid.uuid4()}"
    )
    assert response.status_code == 404


async def test_session_respects_the_difficulty_filter(client):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=3)
    await generate_questions(client, type="MCQ", marks=1, difficulty="hard", count=3)

    session = (
        await client.post("/practice/sessions", json={**SESSION, "count": 3})
    ).json()
    assert all(q["difficulty"] == "easy" for q in session["questions"])


async def test_session_respects_the_type_filter(client):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=3)
    await generate_questions(client, type="Long", marks=5, difficulty="easy", count=3)

    session = (
        await client.post("/practice/sessions", json={**SESSION, "count": 3})
    ).json()
    assert all(q["type"] == "MCQ" for q in session["questions"])


async def test_unknown_session_returns_404(client):
    response = await client.get(f"/practice/sessions/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_invalid_session_request_returns_400(client):
    response = await client.post("/practice/sessions", json={**SESSION, "grade": 12})
    assert response.status_code == 400
    assert set(response.json()) == {"error", "detail"}


# --- syllabus reference data -----------------------------------------------


async def test_subjects_lists_all_five(client):
    response = await client.get("/subjects")
    assert response.status_code == 200

    names = [s["name"] for s in response.json()]
    assert names == sorted(
        ["Math", "Science", "Social Science", "English", "Kannada"], key=names.index
    )
    assert set(names) == {"Math", "Science", "Social Science", "English", "Kannada"}
    assert all(s["grade_range"] == "7-9" for s in response.json())


async def test_chapters_are_empty_before_anything_is_generated(client):
    response = await client.get("/subjects/Science/chapters")
    assert response.status_code == 200
    assert response.json() == []


async def test_chapters_appear_after_generation(client):
    await generate_questions(client, chapter="Photosynthesis", count=2)
    await generate_questions(client, chapter="Force and Pressure", count=3)

    response = await client.get("/subjects/Science/chapters")
    body = response.json()

    by_name = {c["name"]: c for c in body}
    assert set(by_name) == {"Photosynthesis", "Force and Pressure"}
    assert by_name["Photosynthesis"]["question_count"] == 2
    assert by_name["Force and Pressure"]["question_count"] == 3


async def test_chapter_names_are_not_duplicated_by_case(client):
    await generate_questions(client, chapter="Photosynthesis", count=1)
    await generate_questions(client, chapter="photosynthesis", count=1)

    response = await client.get("/subjects/Science/chapters")
    assert len(response.json()) == 1


async def test_unknown_subject_returns_400(client):
    response = await client.get("/subjects/Physics/chapters")
    assert response.status_code == 400


async def test_health_endpoint(client):
    response = await client.get("http://test/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
