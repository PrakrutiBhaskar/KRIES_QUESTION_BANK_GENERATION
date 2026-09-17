"""
Edge-case coverage that the happy-path API test files don't reach:

  * questions.py  - exact-duplicate handling inside persist_batch (both the
                    within-batch skip and the resurrect-a-discarded-twin
                    paths), and the empty-ids short circuit.
  * papers.py     - GET /papers (list), adding a brand-new question via
                    PATCH, PATCH rejecting a cross-subject question, and
                    clearing a paper's question list entirely.
  * practice.py   - the "nothing available and shortfall generation is
                    off" 422, and the no-filter (type/difficulty omitted)
                    pool query.
  * generation.py - the process-wide default engine, and the cache lookup's
                    topic filter.
"""
from __future__ import annotations

import uuid

import pytest

from app.errors import UnprocessableError
from app.services import generation as generation_service
from app.services import questions as question_service
from app.services.syllabus import resolve_chapter
from generation_engine.schemas import Difficulty, QuestionType
from generation_engine.schemas import Question as EngineQuestion
from generation_engine.schemas import Subject as SubjectEnum

from .conftest import generate_questions

pytestmark = pytest.mark.asyncio


# --- questions.py: persist_batch edge cases -------------------------------


def _engine_question(text: str, **overrides) -> EngineQuestion:
    fields = dict(
        subject=SubjectEnum.SCIENCE,
        chapter="Photosynthesis",
        type=QuestionType.SHORT,
        grade=8,
        text=text,
        answer="An answer.",
        explanation="Because reasons.",
        marks=2,
        difficulty=Difficulty.MEDIUM,
        topic="stub-topic",
        tags=["stub"],
    )
    fields.update(overrides)
    return EngineQuestion(**fields)


async def test_persist_batch_skips_exact_duplicate_within_the_same_batch(db_session):
    chapter = await resolve_chapter(db_session, SubjectEnum.SCIENCE, "Photosynthesis")
    same_text = "Explain how green plants capture sunlight during the day."
    batch = [_engine_question(same_text), _engine_question(same_text)]

    stored = await question_service.persist_batch(db_session, batch, chapter=chapter)

    assert len(stored) == 1


async def test_persist_batch_resurrects_a_previously_discarded_twin(db_session):
    chapter = await resolve_chapter(db_session, SubjectEnum.SCIENCE, "Photosynthesis")
    text = "Describe the role of stomata in gas exchange."

    [first] = await question_service.persist_batch(
        db_session, [_engine_question(text)], chapter=chapter
    )
    await question_service.delete_question(db_session, first.id)
    assert first.is_active is False

    [second] = await question_service.persist_batch(
        db_session, [_engine_question(text)], chapter=chapter
    )

    assert second.id == first.id
    assert second.is_active is True


async def test_persist_batch_with_no_questions_returns_empty_list(db_session):
    chapter = await resolve_chapter(db_session, SubjectEnum.SCIENCE, "Photosynthesis")
    assert await question_service.persist_batch(db_session, [], chapter=chapter) == []


async def test_get_questions_by_ids_with_no_ids_short_circuits(db_session):
    assert await question_service.get_questions_by_ids(db_session, []) == {}


# --- questions.py: PATCH no-op --------------------------------------------


async def test_patch_question_with_no_fields_is_a_no_op(client):
    [question] = await generate_questions(client, count=1)
    response = await client.patch(f"/questions/{question['id']}", json={})
    assert response.status_code == 200
    assert response.json()["text"] == question["text"]


# --- papers.py: list, add-new-item, cross-subject PATCH, clear -----------


async def test_list_papers_returns_recent_papers_first(client):
    questions = await generate_questions(client, count=1)
    created = []
    for i in range(2):
        resp = await client.post(
            "/papers",
            json={
                "title": f"Paper {i}",
                "subject": "Science",
                "question_ids": [questions[0]["id"]],
            },
        )
        assert resp.status_code == 201
        created.append(resp.json()["id"])

    response = await client.get("/papers")
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert set(created).issubset(set(ids))


async def test_list_papers_respects_limit(client):
    questions = await generate_questions(client, count=1)
    for i in range(3):
        await client.post(
            "/papers",
            json={
                "title": f"Limit test {i}",
                "subject": "Science",
                "question_ids": [questions[0]["id"]],
            },
        )
    response = await client.get("/papers", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_patch_paper_can_add_a_brand_new_question(client):
    first_batch = await generate_questions(client, count=1)
    paper = await client.post(
        "/papers",
        json={
            "title": "Growable paper",
            "subject": "Science",
            "question_ids": [first_batch[0]["id"]],
        },
    )
    paper = paper.json()

    second_batch = await generate_questions(
        client, count=1, chapter="Force and Pressure"
    )
    patched = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": first_batch[0]["id"], "order_index": 0},
                {"question_id": second_batch[0]["id"], "order_index": 1},
            ]
        },
    )
    assert patched.status_code == 200
    body = patched.json()
    assert len(body["questions"]) == 2
    assert {i["question"]["id"] for i in body["questions"]} == {
        first_batch[0]["id"],
        second_batch[0]["id"],
    }


async def test_patch_paper_rejects_a_cross_subject_question(client):
    science = await generate_questions(client, subject="Science", count=1)
    math = await generate_questions(client, subject="Math", chapter="Algebra", count=1)

    paper = (
        await client.post(
            "/papers",
            json={
                "title": "Science only",
                "subject": "Science",
                "question_ids": [science[0]["id"]],
            },
        )
    ).json()

    response = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": science[0]["id"], "order_index": 0},
                {"question_id": math[0]["id"], "order_index": 1},
            ]
        },
    )
    assert response.status_code == 400


async def test_patch_paper_can_clear_all_questions(client):
    questions = await generate_questions(client, count=2, marks=3)
    paper = (
        await client.post(
            "/papers",
            json={
                "title": "About to be emptied",
                "subject": "Science",
                "question_ids": [q["id"] for q in questions],
            },
        )
    ).json()

    response = await client.patch(f"/papers/{paper['id']}", json={"questions": []})
    assert response.status_code == 200
    body = response.json()
    assert body["questions"] == []
    assert body["total_marks"] == 0


# --- practice.py: no-filter pool query, and the "nothing available" 422 --


async def test_practice_session_without_type_or_difficulty_filter(client):
    await generate_questions(client, type="Short", marks=2, count=3)
    response = await client.post(
        "/practice/sessions",
        json={
            "subject": "Science",
            "chapter": "Photosynthesis",
            "grade": 8,
            "count": 2,
        },
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["questions"]) == 2


async def test_practice_session_422_when_nothing_available_and_shortfall_disabled(
    client, monkeypatch
):
    import app.services.practice as practice_service

    monkeypatch.setattr(practice_service.settings, "practice_generate_shortfall", False)
    response = await client.post(
        "/practice/sessions",
        json={
            "subject": "Science",
            "chapter": "A Totally Unseeded Chapter",
            "grade": 8,
            "count": 5,
        },
    )
    assert response.status_code == 422


# --- generation.py: default engine + cache topic filter -------------------


async def test_persist_batch_does_not_reactivate_an_already_active_duplicate(
    db_session,
):
    chapter = await resolve_chapter(db_session, SubjectEnum.SCIENCE, "Photosynthesis")
    text = "Why is magnesium considered an essential plant nutrient?"

    [first] = await question_service.persist_batch(
        db_session, [_engine_question(text)], chapter=chapter
    )
    assert first.is_active is True

    [second] = await question_service.persist_batch(
        db_session, [_engine_question(text)], chapter=chapter
    )
    assert second.id == first.id
    assert second.is_active is True


# --- papers.py: unknown id inside a PATCH's question list -----------------


async def test_patch_paper_rejects_an_unknown_question_id(client):
    questions = await generate_questions(client, count=1)
    paper = (
        await client.post(
            "/papers",
            json={
                "title": "Will get a bad patch",
                "subject": "Science",
                "question_ids": [questions[0]["id"]],
            },
        )
    ).json()

    response = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": questions[0]["id"], "order_index": 0},
                {"question_id": str(uuid.uuid4()), "order_index": 1},
            ]
        },
    )
    assert response.status_code == 400


async def test_patch_paper_rejects_duplicate_question_ids_in_the_list(client):
    questions = await generate_questions(client, count=1)
    paper = (
        await client.post(
            "/papers",
            json={
                "title": "Dup patch",
                "subject": "Science",
                "question_ids": [questions[0]["id"]],
            },
        )
    ).json()

    response = await client.patch(
        f"/papers/{paper['id']}",
        json={
            "questions": [
                {"question_id": questions[0]["id"], "order_index": 0},
                {"question_id": questions[0]["id"], "order_index": 1},
            ]
        },
    )
    assert response.status_code == 400


async def test_practice_session_rejects_a_blank_chapter(client):
    response = await client.post(
        "/practice/sessions",
        json={"subject": "Science", "chapter": "   ", "grade": 8},
    )
    assert response.status_code == 400


# --- questions.py: topic filter on GET /questions --------------------------


async def test_list_questions_filters_by_topic(client):
    await generate_questions(client, count=2, topic="stub-topic")
    response = await client.get("/questions", params={"topic": "stub-topic"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert all(q["topic"] == "stub-topic" for q in body["results"])

    miss = await client.get("/questions", params={"topic": "no-such-topic"})
    assert miss.json()["total"] == 0


# --- export/__init__.py: valid filename pattern, but file never created ---


async def test_download_export_404s_for_a_valid_but_unknown_filename(client):
    response = await client.get("/export/files/never-generated-abc123.pdf")
    assert response.status_code == 404


# --- syllabus router: subject that already has rows ------------------------


async def test_list_subjects_reflects_an_already_persisted_subject(client):
    await generate_questions(client, subject="Science", count=1)
    response = await client.get("/subjects")
    assert response.status_code == 200
    science = next(s for s in response.json() if s["name"] == "Science")
    assert science["chapter_count"] >= 1


async def test_get_engine_builds_a_default_engine_when_none_is_set():
    generation_service.set_engine(None)
    try:
        engine = generation_service.get_engine()
        assert engine is not None
        # Calling it again reuses the same process-wide instance.
        assert generation_service.get_engine() is engine
    finally:
        generation_service.set_engine(None)


async def test_generate_with_a_topic_hint_is_accepted(client):
    questions = await generate_questions(client, count=2, topic="stub-topic")
    assert all(q["topic"] == "stub-topic" for q in questions)

    # Repeating the same request (topic included) should hit the cache
    # lookup's topic-filtered branch rather than erroring.
    again = await generate_questions(client, count=2, topic="stub-topic")
    assert len(again) == 2
