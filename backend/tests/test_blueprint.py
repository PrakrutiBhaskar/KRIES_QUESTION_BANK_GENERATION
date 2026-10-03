"""
Blueprint-based papers: the allocation arithmetic (pure) and the two endpoints
POST /papers/blueprint and POST /papers/blueprint/preview.
"""
from __future__ import annotations

import pytest

from app.schemas.requests import BlueprintIn
from app.services.blueprint import build_plan

pytestmark = pytest.mark.asyncio

CHAPTERS = ["Photosynthesis", "Respiration", "Transportation"]


def blueprint(**overrides) -> dict:
    body = {
        "title": "Term 1 Science",
        "subject": "Science",
        "grade": 8,
        "chapters": [
            {"name": "Photosynthesis", "weightage": 50},
            {"name": "Respiration", "weightage": 30},
            {"name": "Transportation", "weightage": 20},
        ],
        "sections": [
            {"name": "Section A", "type": "MCQ", "marks_per_question": 1, "total_marks": 10},
            {"name": "Section B", "type": "Short", "marks_per_question": 2, "total_marks": 10},
            {"name": "Section C", "type": "Long", "marks_per_question": 5, "total_marks": 10},
        ],
    }
    body.update(overrides)
    return body


# --- allocation (no database, no LLM) -----------------------------------------


def test_plan_meets_chapter_targets_for_a_board_style_paper():
    bp = BlueprintIn(
        subject="Science",
        grade=8,
        chapters=[
            {"name": "Ch1", "weightage": 40},
            {"name": "Ch2", "weightage": 35},
            {"name": "Ch3", "weightage": 25},
        ],
        sections=[
            {"name": "A", "type": "MCQ", "marks_per_question": 1, "total_marks": 20},
            {"name": "B", "type": "Short", "marks_per_question": 2, "total_marks": 20},
            {"name": "C", "type": "Short", "marks_per_question": 3, "total_marks": 15},
            {"name": "D", "type": "Long", "marks_per_question": 5, "total_marks": 25},
        ],
    )
    plan = build_plan(bp).response

    assert plan.total_marks == 80
    assert plan.total_questions == 20 + 10 + 5 + 5
    assert {c.chapter: c.planned_marks for c in plan.chapters} == {"Ch1": 32, "Ch2": 28, "Ch3": 20}


def test_plan_gives_every_section_exactly_its_question_count():
    bp = BlueprintIn(**blueprint())
    plan = build_plan(bp).response

    for section, spec in zip(plan.sections, bp.sections):
        assert section.questions == spec.question_count
        assert sum(a.questions for a in section.allocations) == spec.question_count
        assert section.marks == spec.total_marks
    # Chapter totals add back up to the paper total.
    assert sum(c.planned_marks for c in plan.chapters) == plan.total_marks


def test_plan_is_deterministic():
    bp = BlueprintIn(**blueprint())
    first = build_plan(bp).response.model_dump()
    assert all(build_plan(bp).response.model_dump() == first for _ in range(5))


def test_plan_reports_the_gap_when_whole_questions_cannot_hit_the_weightage():
    # Two 5-mark questions cannot cover four chapters at 25% each.
    bp = BlueprintIn(
        subject="Science",
        grade=8,
        chapters=[{"name": f"Ch{i}", "weightage": 25} for i in range(1, 5)],
        sections=[{"name": "A", "type": "Long", "marks_per_question": 5, "total_marks": 10}],
    )
    plan = build_plan(bp).response

    assert sorted(c.planned_marks for c in plan.chapters) == [0, 0, 5, 5]
    assert all(c.target_marks == 2.5 for c in plan.chapters)


def test_mixed_difficulty_cycles_through_all_three_levels():
    from app.services.blueprint import _slot_difficulties

    bp = BlueprintIn(
        **blueprint(
            sections=[
                {"name": "A", "type": "Short", "marks_per_question": 2, "total_marks": 12,
                 "difficulty": "mixed"},
            ]
        )
    )
    diffs = _slot_difficulties(bp, build_plan(bp))[0]
    assert diffs == ["easy", "medium", "hard", "easy", "medium", "hard"]


# --- preview endpoint -----------------------------------------------------------


async def test_preview_returns_the_plan_and_generates_nothing(client, groq_stub):
    response = await client.post("/papers/blueprint/preview", json=blueprint())
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["total_marks"] == 30
    assert body["total_questions"] == 10 + 5 + 2
    assert [s["name"] for s in body["sections"]] == ["Section A", "Section B", "Section C"]
    assert groq_stub.calls == []  # no LLM involved

    listing = await client.get("/questions")
    assert listing.json()["total"] == 0  # and nothing stored


# --- creating a paper -----------------------------------------------------------


async def test_blueprint_paper_has_sections_marks_and_chapters_as_specified(client):
    response = await client.post("/papers/blueprint", json=blueprint())
    assert response.status_code == 201, response.text
    paper = response.json()

    assert paper["title"] == "Term 1 Science"
    assert paper["subject"] == "Science"
    assert paper["total_marks"] == 30
    items = paper["questions"]
    assert len(items) == 17

    # Section order, and every question carries its section.
    sections = [i["section"] for i in items]
    assert sections == ["Section A"] * 10 + ["Section B"] * 5 + ["Section C"] * 2
    assert [i["order_index"] for i in items] == list(range(17))

    # Each section holds the right kind of question at the right marks.
    by_section: dict[str, list[dict]] = {}
    for item in items:
        by_section.setdefault(item["section"], []).append(item)
    assert {i["question"]["type"] for i in by_section["Section A"]} == {"MCQ"}
    assert {i["marks"] for i in by_section["Section B"]} == {2}
    assert {i["question"]["type"] for i in by_section["Section C"]} == {"Long"}

    # Chapter weightage is honoured: 50 / 30 / 20 of 30 marks.
    marks_by_chapter: dict[str, int] = {}
    for item in items:
        chapter = item["question"]["chapter"]
        marks_by_chapter[chapter] = marks_by_chapter.get(chapter, 0) + item["marks"]
    assert marks_by_chapter == {"Photosynthesis": 15, "Respiration": 9, "Transportation": 6}


async def test_blueprint_paper_uses_distinct_questions(client):
    paper = (await client.post("/papers/blueprint", json=blueprint())).json()
    ids = [i["question"]["id"] for i in paper["questions"]]
    assert len(ids) == len(set(ids))


async def test_two_sections_asking_for_the_same_kind_of_question_do_not_collide(client):
    body = blueprint(
        chapters=[{"name": "Photosynthesis", "weightage": 100}],
        sections=[
            {"name": "Part 1", "type": "Short", "marks_per_question": 2, "total_marks": 6},
            {"name": "Part 2", "type": "Short", "marks_per_question": 2, "total_marks": 6},
        ],
    )
    response = await client.post("/papers/blueprint", json=body)
    assert response.status_code == 201, response.text

    items = response.json()["questions"]
    assert [i["section"] for i in items] == ["Part 1"] * 3 + ["Part 2"] * 3
    assert len({i["question"]["id"] for i in items}) == 6


async def test_default_title_when_none_is_given(client):
    body = blueprint()
    del body["title"]
    paper = (await client.post("/papers/blueprint", json=body)).json()
    assert paper["title"] == "Science Question Paper (Grade 8)"


async def test_blueprint_paper_is_listed_and_private_to_its_owner(client, bob_client):
    created = (await client.post("/papers/blueprint", json=blueprint())).json()

    mine = (await client.get("/papers")).json()
    assert [p["id"] for p in mine] == [created["id"]]
    assert (await bob_client.get("/papers")).json() == []
    assert (await bob_client.get(f"/papers/{created['id']}")).status_code == 404


async def test_questions_stay_in_their_sections_after_a_reorder_patch(client):
    paper = (await client.post("/papers/blueprint", json=blueprint())).json()
    ids = [i["question"]["id"] for i in paper["questions"]]

    # Drop one question and send the rest back in the same order, like the
    # frontend does when a question is removed from a bank.
    kept = ids[1:]
    response = await client.patch(
        f"/papers/{paper['id']}",
        json={"questions": [{"question_id": q, "order_index": n} for n, q in enumerate(kept)]},
    )
    assert response.status_code == 200, response.text
    items = response.json()["questions"]
    assert [i["section"] for i in items] == (["Section A"] * 9 + ["Section B"] * 5 + ["Section C"] * 2)


async def test_papers_built_by_hand_have_no_sections(client):
    from .conftest import generate_questions

    questions = await generate_questions(client, count=2)
    paper = (
        await client.post(
            "/papers",
            json={"title": "By hand", "subject": "Science", "question_ids": [q["id"] for q in questions]},
        )
    ).json()
    assert [i["section"] for i in paper["questions"]] == [None, None]


async def test_generated_questions_are_reused_on_the_next_paper(client, groq_stub):
    await client.post("/papers/blueprint", json=blueprint())
    calls_after_first = len(groq_stub.calls)
    assert calls_after_first > 0

    second = await client.post("/papers/blueprint", json=blueprint(title="Again"))
    assert second.status_code == 201, second.text
    assert len(groq_stub.calls) == calls_after_first  # served from storage

    forced = await client.post("/papers/blueprint", json=blueprint(title="Fresh", refresh=True))
    assert forced.status_code == 201, forced.text
    assert len(groq_stub.calls) > calls_after_first  # refresh asks the LLM again


# --- validation: everything here must fail before any question is generated ----


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            {"chapters": [{"name": "A", "weightage": 50}, {"name": "B", "weightage": 40}]},
            "add up to 100",
        ),
        (
            {"chapters": [{"name": "A", "weightage": 50}, {"name": "a", "weightage": 50}]},
            "must not repeat",
        ),
        ({"chapters": []}, "chapters"),
        ({"sections": []}, "sections"),
        (
            {"sections": [{"name": "A", "type": "MCQ", "marks_per_question": 2, "total_marks": 10}]},
            "MCQ questions must use marks",
        ),
        (
            {"sections": [{"name": "A", "type": "Long", "marks_per_question": 5, "total_marks": 12}]},
            "whole number",
        ),
        (
            {
                "sections": [
                    {"name": "A", "type": "MCQ", "marks_per_question": 1, "total_marks": 5},
                    {"name": "a", "type": "Short", "marks_per_question": 2, "total_marks": 4},
                ]
            },
            "section names must be unique",
        ),
        (
            {"sections": [{"name": "A", "type": "MCQ", "marks_per_question": 1, "total_marks": 101}]},
            "at most 100 questions",
        ),
        ({"grade": 10}, "grade"),
    ],
)
async def test_invalid_blueprints_are_rejected_with_a_400_and_no_llm_calls(
    client, groq_stub, mutation, expected
):
    for path in ("/papers/blueprint", "/papers/blueprint/preview"):
        response = await client.post(path, json=blueprint(**mutation))
        assert response.status_code == 400, response.text
        body = response.json()
        assert body["error"] == "invalid_request"
        assert expected in body["detail"]
    assert groq_stub.calls == []


async def test_unknown_fields_are_rejected(client):
    response = await client.post("/papers/blueprint", json=blueprint(surprise=True))
    assert response.status_code == 400


async def test_blueprint_endpoints_require_sign_in(anon_client):
    for path in ("/papers/blueprint", "/papers/blueprint/preview"):
        assert (await anon_client.post(path, json=blueprint())).status_code == 401


# --- failure is all-or-nothing --------------------------------------------------


async def test_llm_failure_returns_502_and_stores_no_paper_or_questions(failing_client):
    response = await failing_client.post("/papers/blueprint", json=blueprint())
    assert response.status_code == 502

    assert (await failing_client.get("/papers")).json() == []
    assert (await failing_client.get("/questions")).json()["total"] == 0


async def test_unusable_llm_output_returns_422(bad_payload_client):
    response = await bad_payload_client.post("/papers/blueprint", json=blueprint())
    assert response.status_code == 422
    assert (await bad_payload_client.get("/papers")).json() == []


# --- export ---------------------------------------------------------------------


async def test_html_and_pdf_show_section_headings(client, db_session):
    import uuid

    from sqlalchemy import select

    from app.models import Paper
    from app.services.export import render_paper_html, render_pdf

    paper_json = (await client.post("/papers/blueprint", json=blueprint())).json()
    paper = await db_session.scalar(select(Paper).where(Paper.id == uuid.UUID(paper_json["id"])))

    html = render_paper_html(paper)
    for heading in ("Section A", "Section B", "Section C"):
        assert f"<span>{heading}</span>" in html
    assert "<span>10 marks</span>" in html  # each section is worth 10

    assert render_pdf(paper).startswith(b"%PDF")

    export = await client.post(f"/export/{paper_json['id']}")
    assert export.status_code == 200, export.text


# --- background builds with progress -------------------------------------------


async def _wait_for_job(client, job_id: str, *, timeout: float = 10.0) -> tuple[dict, list[tuple[int, int]]]:
    """Wait for the job to leave 'running'; returns its final GET plus every (done, total) seen.

    While it runs we watch the in-process record instead of polling over HTTP:
    the suite's in-memory database is a single shared connection, so a poll's own
    database read would collide with the build's commit. (Real databases give each
    session its own connection.) The final GET goes through the API as usual.
    """
    import asyncio
    import uuid

    from app.services import blueprint_jobs

    job = blueprint_jobs._jobs[uuid.UUID(job_id)]
    seen: list[tuple[int, int]] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while job.status == "running":
        seen.append((job.done, job.total))
        assert asyncio.get_event_loop().time() < deadline, "job never finished"
        await asyncio.sleep(0.005)
    seen.append((job.done, job.total))
    return (await client.get(f"/papers/blueprint/jobs/{job_id}")).json(), seen


async def test_background_build_reports_progress_and_returns_the_paper(client):
    started = await client.post("/papers/blueprint/jobs", json=blueprint())
    assert started.status_code == 202
    job, seen = await _wait_for_job(client, started.json()["id"])

    assert job["status"] == "done"
    assert job["total"] > 0
    assert job["done"] == job["total"]
    # Progress never goes backwards.
    dones = [d for d, _ in seen]
    assert dones == sorted(dones)

    paper = job["paper"]
    assert paper["total_marks"] == 30
    assert len(paper["questions"]) == job["total"]
    # It is a real, saved paper.
    assert (await client.get(f"/papers/{paper['id']}")).status_code == 200


async def test_background_build_matches_the_one_shot_endpoint(client):
    job_id = (await client.post("/papers/blueprint/jobs", json=blueprint())).json()["id"]
    job, _ = await _wait_for_job(client, job_id)
    one_shot = (await client.post("/papers/blueprint", json=blueprint())).json()
    sections = lambda p: [q["section"] for q in sorted(p["questions"], key=lambda q: q["order_index"])]  # noqa: E731
    assert sections(job["paper"]) == sections(one_shot)


async def test_background_build_reports_an_llm_failure_and_stores_nothing(failing_client):
    job_id = (await failing_client.post("/papers/blueprint/jobs", json=blueprint())).json()["id"]
    job, _ = await _wait_for_job(failing_client, job_id)
    assert job["status"] == "error"
    assert job["error_status"] == 502
    assert job["paper"] is None
    assert (await failing_client.get("/papers")).json() == []


async def test_only_one_build_at_a_time_per_user(client, monkeypatch):
    import asyncio

    gate = asyncio.Event()

    async def slow(session, bp, user_id, on_progress=None):
        on_progress(3, 30)
        await gate.wait()
        raise RuntimeError("released")

    monkeypatch.setattr("app.services.blueprint.create_blueprint_paper", slow)
    first = await client.post("/papers/blueprint/jobs", json=blueprint())
    assert first.status_code == 202
    second = await client.post("/papers/blueprint/jobs", json=blueprint())
    assert second.status_code == 409
    assert second.json()["error"] == "paper_in_progress"

    # While it runs the poll shows how far it got.
    await asyncio.sleep(0.05)
    running = (await client.get(f"/papers/blueprint/jobs/{first.json()['id']}")).json()
    assert (running["status"], running["done"], running["total"]) == ("running", 3, 30)

    gate.set()
    job, _ = await _wait_for_job(client, first.json()["id"])
    assert job["status"] == "error" and job["error_status"] == 500
    # A finished job frees the slot.
    assert (await client.post("/papers/blueprint/jobs", json=blueprint())).status_code in (202, 409)


async def test_a_job_is_private_to_its_owner(client, bob_client):
    job_id = (await client.post("/papers/blueprint/jobs", json=blueprint())).json()["id"]
    assert (await bob_client.get(f"/papers/blueprint/jobs/{job_id}")).status_code == 404
    await _wait_for_job(client, job_id)


async def test_unknown_job_is_a_404(client):
    import uuid

    assert (await client.get(f"/papers/blueprint/jobs/{uuid.uuid4()}")).status_code == 404


async def test_job_endpoints_validate_and_require_sign_in(client, anon_client):
    assert (await client.post("/papers/blueprint/jobs", json=blueprint(surprise=True))).status_code == 400
    assert (await anon_client.post("/papers/blueprint/jobs", json=blueprint())).status_code == 401
