"""
Paper builder and export — test-plan.md Section 2, rows for `POST /papers`,
`PATCH /papers/{id}` and `POST /export/{paper_id}`.
"""
from __future__ import annotations

import uuid

import pytest

from .conftest import generate_questions

pytestmark = pytest.mark.asyncio


async def _paper(client, *, count: int = 3, **overrides):
    questions = await generate_questions(client, count=count, **overrides)
    response = await client.post(
        "/papers",
        json={
            "title": "Science Unit Test - Chapter 3",
            "subject": overrides.get("subject", "Science"),
            "question_ids": [q["id"] for q in questions],
        },
    )
    assert response.status_code == 201, response.text
    return response.json(), questions


# --- creation --------------------------------------------------------------


async def test_paper_created_with_correct_order_and_marks(client):
    paper, questions = await _paper(client, count=3, marks=3)

    assert paper["title"] == "Science Unit Test - Chapter 3"
    assert paper["subject"] == "Science"
    assert [item["order_index"] for item in paper["questions"]] == [0, 1, 2]
    # Order follows the order the ids were sent in.
    assert [item["question"]["id"] for item in paper["questions"]] == [
        q["id"] for q in questions
    ]
    # 3 questions x 3 marks
    assert paper["total_marks"] == 9


async def test_total_marks_sums_mixed_mark_values(client):
    mcqs = await generate_questions(client, type="MCQ", marks=1, count=2)
    longs = await generate_questions(client, type="Long", marks=5, count=1)

    response = await client.post(
        "/papers",
        json={
            "title": "Mixed paper",
            "subject": "Science",
            "question_ids": [q["id"] for q in mcqs + longs],
        },
    )
    assert response.json()["total_marks"] == 1 + 1 + 5


async def test_client_supplied_total_marks_must_agree(client):
    questions = await generate_questions(client, marks=3, count=2)
    response = await client.post(
        "/papers",
        json={
            "title": "Wrong total",
            "subject": "Science",
            "question_ids": [q["id"] for q in questions],
            "total_marks": 99,
        },
    )
    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]


async def test_matching_total_marks_is_accepted(client):
    questions = await generate_questions(client, marks=3, count=2)
    response = await client.post(
        "/papers",
        json={
            "title": "Right total",
            "subject": "Science",
            "question_ids": [q["id"] for q in questions],
            "total_marks": 6,
        },
    )
    assert response.status_code == 201


async def test_unknown_question_id_is_rejected(client):
    response = await client.post(
        "/papers",
        json={
            "title": "Bad paper",
            "subject": "Science",
            "question_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 400


async def test_mixing_subjects_is_rejected(client):
    science = await generate_questions(client, subject="Science", count=1)
    math = await generate_questions(client, subject="Math", chapter="Algebra", count=1)

    response = await client.post(
        "/papers",
        json={
            "title": "Cross-subject",
            "subject": "Science",
            "question_ids": [science[0]["id"], math[0]["id"]],
        },
    )
    assert response.status_code == 400


async def test_duplicate_question_ids_are_rejected(client):
    questions = await generate_questions(client, count=1)
    response = await client.post(
        "/papers",
        json={
            "title": "Repeat",
            "subject": "Science",
            "question_ids": [questions[0]["id"], questions[0]["id"]],
        },
    )
    assert response.status_code == 400


async def test_discarded_question_cannot_be_added(client):
    questions = await generate_questions(client, count=2)
    await client.delete(f"/questions/{questions[0]['id']}")

    response = await client.post(
        "/papers",
        json={
            "title": "Uses a discarded question",
            "subject": "Science",
            "question_ids": [q["id"] for q in questions],
        },
    )
    assert response.status_code == 400


# --- retrieval / editing ---------------------------------------------------


async def test_get_paper(client):
    paper, _ = await _paper(client)
    response = await client.get(f"/papers/{paper['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == paper["id"]


async def test_get_unknown_paper_returns_404(client):
    response = await client.get(f"/papers/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_reorder_persists(client):
    paper, questions = await _paper(client, count=3, marks=3)
    reversed_ids = [q["id"] for q in reversed(questions)]

    patched = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": qid, "order_index": i}
                for i, qid in enumerate(reversed_ids)
            ]
        },
    )
    assert patched.status_code == 200
    assert [i["question"]["id"] for i in patched.json()["questions"]] == reversed_ids

    refetched = await client.get(f"/papers/{paper['id']}")
    assert [i["question"]["id"] for i in refetched.json()["questions"]] == reversed_ids


async def test_sparse_order_indexes_are_renumbered_densely(client):
    paper, questions = await _paper(client, count=3, marks=3)

    patched = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": questions[0]["id"], "order_index": 50},
                {"question_id": questions[1]["id"], "order_index": 10},
                {"question_id": questions[2]["id"], "order_index": 30},
            ]
        },
    )
    body = patched.json()
    assert [i["order_index"] for i in body["questions"]] == [0, 1, 2]
    # Sorted by the requested index, so 10 < 30 < 50.
    assert [i["question"]["id"] for i in body["questions"]] == [
        questions[1]["id"], questions[2]["id"], questions[0]["id"]
    ]


async def test_marks_override_recalculates_the_total(client):
    paper, questions = await _paper(client, count=2, marks=3)
    assert paper["total_marks"] == 6

    patched = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": questions[0]["id"], "order_index": 0, "marks_override": 5},
                {"question_id": questions[1]["id"], "order_index": 1},
            ]
        },
    )
    body = patched.json()
    assert body["total_marks"] == 8
    assert body["questions"][0]["marks"] == 5
    assert body["questions"][0]["marks_override"] == 5
    # The underlying question is untouched — the override is paper-local.
    assert body["questions"][0]["question"]["marks"] == 3


async def test_removing_a_question_updates_the_total(client):
    paper, questions = await _paper(client, count=3, marks=3)

    patched = await client.patch(
        f"/papers/{paper['id']}",
        json={"questions": [{"question_id": questions[0]["id"], "order_index": 0}]},
    )
    assert len(patched.json()["questions"]) == 1
    assert patched.json()["total_marks"] == 3


async def test_rename_persists(client):
    paper, _ = await _paper(client)
    patched = await client.patch(f"/papers/{paper['id']}", json={"title": "Renamed"})
    assert patched.json()["title"] == "Renamed"


async def test_invalid_marks_override_is_rejected(client):
    paper, questions = await _paper(client, count=1, marks=3)
    response = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": questions[0]["id"], "order_index": 0, "marks_override": 4}
            ]
        },
    )
    assert response.status_code == 400


# --- export ----------------------------------------------------------------


async def test_export_returns_a_downloadable_pdf(client):
    paper, _ = await _paper(client, count=3, marks=3)

    response = await client.post(f"/export/{paper['id']}")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["download_url"].endswith(body["filename"])
    assert body["filename"].endswith(".pdf")
    assert body["size_bytes"] > 0

    download = await client.get(f"/export/files/{body['filename']}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    # PDF magic number — this is a real document, not an empty file.
    assert download.content.startswith(b"%PDF-")


async def test_export_handles_a_large_paper(client):
    """test-plan.md Section 5: export shouldn't break on a long paper."""
    questions = await generate_questions(client, type="MCQ", marks=1, count=25)
    paper = await client.post(
        "/papers",
        json={
            "title": "Full length MCQ paper",
            "subject": "Science",
            "question_ids": [q["id"] for q in questions],
        },
    )
    response = await client.post(f"/export/{paper.json()['id']}")
    assert response.status_code == 200
    assert response.json()["size_bytes"] > 0


async def test_export_unknown_paper_returns_404(client):
    response = await client.post(f"/export/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_download_rejects_path_traversal(client):
    response = await client.get("/export/files/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code == 404
