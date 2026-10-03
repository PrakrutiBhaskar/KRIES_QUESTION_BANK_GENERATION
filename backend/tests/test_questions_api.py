"""
Question bank endpoints — test-plan.md Section 2, rows for
`GET /questions`, `PATCH /questions/{id}` and `DELETE /questions/{id}`.
"""
from __future__ import annotations

import uuid

import pytest

from .conftest import generate_questions

pytestmark = pytest.mark.asyncio


# --- retrieval / filtering -------------------------------------------------


async def test_empty_bank_returns_empty_page(client):
    response = await client.get("/questions")
    assert response.status_code == 200
    assert response.json() == {"results": [], "total": 0, "page": 1, "page_size": 20}


async def test_filters_apply_individually(client):
    await generate_questions(client, type="MCQ", marks=1, count=2)
    await generate_questions(client, type="Long", marks=5, count=2)

    mcqs = await client.get("/questions", params={"type": "MCQ"})
    assert mcqs.json()["total"] == 2
    assert all(q["type"] == "MCQ" for q in mcqs.json()["results"])

    longs = await client.get("/questions", params={"marks": 5})
    assert longs.json()["total"] == 2


async def test_filters_compose(client):
    await generate_questions(client, type="MCQ", marks=1, difficulty="easy", count=2)
    await generate_questions(client, type="MCQ", marks=1, difficulty="hard", count=3)

    response = await client.get(
        "/questions",
        params={"subject": "Science", "type": "MCQ", "difficulty": "hard", "grade": 8},
    )
    assert response.json()["total"] == 3


async def test_filter_across_subjects_is_isolated(client):
    await generate_questions(client, subject="Science", count=2)
    await generate_questions(client, subject="Math", chapter="Algebra", count=3)

    response = await client.get("/questions", params={"subject": "Math"})
    body = response.json()
    assert body["total"] == 3
    assert all(q["subject"] == "Math" for q in body["results"])


async def test_chapter_filter_is_case_insensitive(client):
    await generate_questions(client, count=2)
    response = await client.get("/questions", params={"chapter": "photosynthesis"})
    assert response.json()["total"] == 2


async def test_search_matches_question_text(client):
    questions = await generate_questions(client, count=3)
    needle = questions[0]["text"].split()[1]

    response = await client.get("/questions", params={"search": needle})
    assert response.json()["total"] >= 1


async def test_non_matching_filter_returns_empty(client):
    await generate_questions(client, count=2)
    response = await client.get("/questions", params={"grade": 9})
    assert response.json()["total"] == 0
    assert response.json()["results"] == []


async def test_pagination_splits_results(client):
    await generate_questions(client, count=5)

    first = await client.get("/questions", params={"page": 1, "page_size": 2})
    second = await client.get("/questions", params={"page": 2, "page_size": 2})
    third = await client.get("/questions", params={"page": 3, "page_size": 2})

    assert first.json()["total"] == 5
    assert len(first.json()["results"]) == 2
    assert len(second.json()["results"]) == 2
    assert len(third.json()["results"]) == 1

    ids = {q["id"] for q in first.json()["results"]}
    assert ids.isdisjoint({q["id"] for q in second.json()["results"]})


async def test_get_single_question(client):
    created = (await generate_questions(client, count=1))[0]
    response = await client.get(f"/questions/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_unknown_question_returns_404(client):
    response = await client.get(f"/questions/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


# --- editing ---------------------------------------------------------------


async def test_edit_persists(client):
    created = (await generate_questions(client, count=1))[0]
    new_text = "Explain, in your own words, how a leaf makes food."

    patched = await client.patch(
        f"/questions/{created['id']}", json={"text": new_text, "topic": "revised"}
    )
    assert patched.status_code == 200
    assert patched.json()["text"] == new_text

    refetched = await client.get(f"/questions/{created['id']}")
    assert refetched.json()["text"] == new_text
    assert refetched.json()["topic"] == "revised"


async def test_edit_rejects_a_marks_format_violation(client):
    """The stored 3-point answer can't satisfy a 1-mark question — a 400."""
    created = (await generate_questions(client, marks=3, count=1))[0]

    response = await client.patch(f"/questions/{created['id']}", json={"marks": 1})
    assert response.status_code == 400
    assert set(response.json()) == {"error", "detail"}
    assert (await client.get(f"/questions/{created['id']}")).json()["marks"] == 3


async def test_the_answer_cannot_be_edited(client):
    created = (await generate_questions(client, count=1))[0]

    response = await client.patch(
        f"/questions/{created['id']}", json={"answer": "A different answer."}
    )
    assert response.status_code == 400
    assert set(response.json()) == {"error", "detail"}
    assert "answer cannot be edited" in response.json()["detail"]
    # Nothing was changed.
    assert (await client.get(f"/questions/{created['id']}")).json()["answer"] == created["answer"]


async def test_the_answer_cannot_be_edited_even_alongside_other_changes(client):
    created = (await generate_questions(client, count=1))[0]

    response = await client.patch(
        f"/questions/{created['id']}",
        json={"topic": "revised", "answer": "A different answer."},
    )
    assert response.status_code == 400
    stored = (await client.get(f"/questions/{created['id']}")).json()
    assert stored["answer"] == created["answer"]
    assert stored["topic"] == created["topic"]  # the whole edit is refused


@pytest.mark.parametrize("value", ["", None, "   "])
async def test_an_empty_answer_field_is_refused_too(client, value):
    created = (await generate_questions(client, count=1))[0]
    response = await client.patch(f"/questions/{created['id']}", json={"answer": value})
    assert response.status_code == 400


async def test_a_verified_badge_survives_edits_to_other_fields(client, db_session):
    from sqlalchemy import update

    from app.models import Question

    created = (await generate_questions(client, count=1))[0]
    await db_session.execute(
        update(Question)
        .where(Question.id == uuid.UUID(created["id"]))
        .values(verification_status="verified", verification_note="Checked by a rule.")
    )
    await db_session.commit()

    response = await client.patch(f"/questions/{created['id']}", json={"topic": "revised"})
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "verified"
    assert body["answer"] == created["answer"]


async def test_edit_rejects_blank_text(client):
    created = (await generate_questions(client, count=1))[0]
    response = await client.patch(f"/questions/{created['id']}", json={"text": "   "})
    assert response.status_code == 400


async def test_edit_rejects_unknown_field(client):
    created = (await generate_questions(client, count=1))[0]
    response = await client.patch(
        f"/questions/{created['id']}", json={"subject": "Math"}
    )
    assert response.status_code == 400


async def test_edit_rejects_mcq_options_that_drop_the_correct_answer(client):
    """With the answer fixed, the options can't be edited out from under it."""
    created = (await generate_questions(client, type="MCQ", marks=1, count=1))[0]
    wrong_only = [o for o in created["options"] if o != created["answer"]]
    response = await client.patch(
        f"/questions/{created['id']}",
        json={"options": wrong_only + ["Another wrong option"]},
    )
    assert response.status_code == 400
    assert (await client.get(f"/questions/{created['id']}")).json()["options"] == created["options"]


async def test_edit_unknown_question_returns_404(client):
    response = await client.patch(f"/questions/{uuid.uuid4()}", json={"topic": "x"})
    assert response.status_code == 404


# --- discarding ------------------------------------------------------------


async def test_delete_removes_from_listings(client):
    created = (await generate_questions(client, count=2))[0]

    response = await client.delete(f"/questions/{created['id']}")
    assert response.status_code == 204

    listing = await client.get("/questions")
    assert listing.json()["total"] == 1
    assert created["id"] not in {q["id"] for q in listing.json()["results"]}


async def test_delete_twice_returns_404(client):
    created = (await generate_questions(client, count=1))[0]
    await client.delete(f"/questions/{created['id']}")

    second = await client.delete(f"/questions/{created['id']}")
    assert second.status_code == 404


async def test_delete_unknown_question_returns_404(client):
    response = await client.delete(f"/questions/{uuid.uuid4()}")
    assert response.status_code == 404
