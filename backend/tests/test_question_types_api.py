"""
Fill in the blank and Match the following through the HTTP API, the stored
rows, the exports and the database migration. The engine-level rules live in
tests/test_question_types.py at the repo root; these check that the backend
carries the two new types end to end.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from app.services.export import html as html_service
from app.services.export import renderer as renderer_service
from generation_engine.schemas import match_left_items, parse_match_answer

from .conftest import generate_questions

pytestmark = pytest.mark.asyncio

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def option_for(question: dict, number: int) -> str:
    letter = parse_match_answer(question["answer"])[number]
    return question["options"]["ABCDE".index(letter)]


# --- the combinations the frontend builds its selectors from -----------------


async def test_combinations_list_the_new_types(client):
    rows = {r["type"]: r["marks"] for r in (await client.get("/generation/combinations")).json()}
    assert rows["Fill"] == [1]
    assert rows["Match"] == [3, 5]
    assert rows["MCQ"] == [1]
    assert rows["Short"] == [1, 2, 3]
    assert rows["Long"] == [3, 5]


@pytest.mark.parametrize(
    "q_type,marks",
    [("Fill", 2), ("Fill", 4), ("Match", 1), ("Match", 2), ("Match", 4), ("MCQ", 2), ("MCQ", 3), ("MCQ", 4), ("Long", 1), ("Short", 5)],
)
async def test_unsupported_marks_for_the_new_types_are_a_400(client, groq_stub, q_type, marks):
    body = {
        "subject": "Science", "chapter": "Photosynthesis", "type": q_type,
        "grade": 8, "marks": marks, "difficulty": "easy", "count": 2,
    }
    response = await client.post("/generate", json=body)
    assert response.status_code == 400, response.text
    assert groq_stub.calls == []


# --- generating and storing --------------------------------------------------


async def test_generate_fill_in_the_blank(client):
    questions = await generate_questions(client, type="Fill", marks=1, count=3)
    assert len(questions) == 3
    for q in questions:
        assert q["type"] == "Fill" and q["marks"] == 1
        assert q["text"].count("_____") == 1
        assert q["options"] is None
        assert q["answer"] and not q["explanation"]


@pytest.mark.parametrize("marks", [3, 5])
async def test_generate_match_the_following(client, marks):
    questions = await generate_questions(client, type="Match", marks=marks, count=2)
    assert len(questions) == 2
    for q in questions:
        assert q["type"] == "Match" and q["marks"] == marks
        assert len(match_left_items(q["text"])) == marks
        assert len(q["options"]) == marks
        mapping = parse_match_answer(q["answer"])
        assert sorted(mapping) == list(range(1, marks + 1))
        assert sorted(mapping.values()) == list("ABCDE"[:marks])
        # the key sends each numbered item to a different option
        assert len({option_for(q, n) for n in mapping}) == marks


async def test_match_key_pairs_the_item_the_model_paired(client):
    """The model says item k goes with right k. Column B is shuffled for print,
    but the stored key must still send each item to the right the model paired it with."""
    q = (await generate_questions(client, type="Match", marks=3, count=1))[0]
    for number in (1, 2, 3):
        # the stub names its rights "Description <index>-<k>", k being the item's
        # position in the model's own (correct) order
        assert option_for(q, number).split()[1].endswith(f"-{number - 1}")
    # and Column B really was shuffled away from that order
    assert [o.split()[1][-1] for o in q["options"]] != ["0", "1", "2"]


async def test_new_types_are_stored_and_filterable(client):
    await generate_questions(client, type="Fill", marks=1, count=2)
    await generate_questions(client, type="Match", marks=3, count=2)
    await generate_questions(client, type="MCQ", marks=1, count=2)

    fill = (await client.get("/questions", params={"type": "Fill"})).json()
    match = (await client.get("/questions", params={"type": "Match"})).json()
    assert fill["total"] == 2 and {q["type"] for q in fill["results"]} == {"Fill"}
    assert match["total"] == 2 and {q["type"] for q in match["results"]} == {"Match"}
    # Column B survives the round trip through the database
    assert all(len(q["options"]) == 3 for q in match["results"])


async def test_stored_questions_are_reused_not_regenerated(client, groq_stub):
    await generate_questions(client, type="Match", marks=3, count=2)
    calls = len(groq_stub.calls)
    again = await client.post(
        "/generate",
        json={"subject": "Science", "chapter": "Photosynthesis", "type": "Match",
              "grade": 8, "marks": 3, "difficulty": "medium", "count": 2},
    )
    assert again.json()["cached"] == 2
    assert len(groq_stub.calls) == calls


# --- editing -----------------------------------------------------------------


async def test_editing_a_match_question_keeps_the_columns_consistent(client):
    q = (await generate_questions(client, type="Match", marks=3, count=1))[0]

    ok = await client.patch(f"/questions/{q['id']}", json={"topic": "Revised topic"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["answer"] == q["answer"]  # still the generated, verified key

    # Dropping an option would leave the key pointing at a letter that is gone.
    bad = await client.patch(f"/questions/{q['id']}", json={"options": q["options"][:2]})
    assert bad.status_code == 400
    # So would deleting a numbered item from the text.
    short_text = "\n".join(q["text"].splitlines()[:-1])
    assert (await client.patch(f"/questions/{q['id']}", json={"text": short_text})).status_code == 400


async def test_editing_a_fill_question_must_keep_one_blank(client):
    q = (await generate_questions(client, type="Fill", marks=1, count=1))[0]
    bad = await client.patch(
        f"/questions/{q['id']}", json={"text": "This sentence has lost its blank entirely."}
    )
    assert bad.status_code == 400
    good = await client.patch(
        f"/questions/{q['id']}", json={"text": "A reworded sentence with the blank _____ kept in."}
    )
    assert good.status_code == 200


# --- preferences and practice ------------------------------------------------


@pytest.mark.parametrize("choice", ["Fill", "Match"])
async def test_default_question_type_preference_accepts_the_new_types(client, choice):
    r = await client.patch("/auth/me", json={"preferences": {"default_question_type": choice}})
    assert r.status_code == 200, r.text
    assert (await client.get("/auth/me")).json()["preferences"]["default_question_type"] == choice


async def test_practice_session_can_fill_a_shortfall_with_the_new_types(client, practice_shortfall_on):
    base = {"subject": "Science", "chapter": "Photosynthesis", "grade": 8,
            "difficulty": "easy", "count": 2}
    for q_type, marks in (("Fill", 1), ("Match", 3)):
        response = await client.post("/practice/sessions", json={**base, "type": q_type})
        assert response.status_code == 201, response.text
        questions = response.json()["questions"]
        assert len(questions) == 2
        assert {q["type"] for q in questions} == {q_type}
        assert {q["marks"] for q in questions} == {marks}
        # practice never shows the key up front
        assert all("answer" not in q for q in questions)


# --- papers and exports ------------------------------------------------------


async def _mixed_paper(client, db_session):
    from app.models import Paper

    fill = await generate_questions(client, type="Fill", marks=1, count=2)
    match = await generate_questions(client, type="Match", marks=3, count=2)
    mcq = await generate_questions(client, type="MCQ", marks=1, count=1)
    response = await client.post(
        "/papers",
        json={
            "title": "Types Paper",
            "subject": "Science",
            "question_ids": [q["id"] for q in fill + match + mcq],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["total_marks"] == 2 + 6 + 1
    paper = await db_session.get(Paper, uuid.UUID(response.json()["id"]))
    return paper, match


async def test_html_export_keeps_columns_and_shows_a_lettered_key(client, db_session):
    paper, match = await _mixed_paper(client, db_session)
    out = html_service.render_paper_html(paper)

    assert "white-space: pre-line" in html_service._STYLE  # one numbered item per line
    # Match the Following is printed as a two-column table, not a list
    assert "<table class='match'>" in out
    assert "<th>Column A</th><th>Column B</th>" in out
    assert "<li>(a)" not in out.split("<table class='match'>")[1].split("</table>")[0]
    assert "fill-in-the-blank questions, write the missing word" in out
    assert "match-the-following questions, write the letter" in out
    # Column B prints as (a) (b) (c), and the key uses the same lowercase letters
    first = match[0]
    letters = [x.lower() for x in "ABC"]
    for letter, option in zip(letters, first["options"]):
        assert f"({letter}) {option}" in out
    key = parse_match_answer(first["answer"])
    assert " - ".join(["1", key[1].lower()]) in out
    assert "_____" in out  # the blank is printed


@pytest.mark.parametrize("choice", ["reportlab", "fpdf"])
async def test_pdf_export_prints_match_and_fill_questions(client, db_session, monkeypatch, choice):
    from app.services.export.fpdf_renderer import fpdf_available
    from .test_export_rendering import _pdf_text

    if choice == "fpdf" and not fpdf_available():
        pytest.skip("fpdf2/uharfbuzz not installed")
    monkeypatch.setattr(renderer_service.settings, "pdf_renderer", choice)
    monkeypatch.setattr(renderer_service, "weasyprint_available", lambda: False)
    paper, match = await _mixed_paper(client, db_session)

    text = _pdf_text(renderer_service.render_pdf(paper))
    flat = " ".join(text.split())

    assert "match-the-following questions" in flat
    assert "fill-in-the-blank questions" in flat
    assert "_____" in text
    # Match the Following is a table with Column A / Column B headings
    assert "Column A" in flat and "Column B" in flat
    # Column A is laid out one numbered item per line, not run together in a paragraph
    left = match_left_items(match[0]["text"])
    assert re.search(rf"^\s*1\.\s*{re.escape(left[0][:20])}", text, re.M), text
    # Column B and the key
    assert f"(a) {match[0]['options'][0]}" in flat
    key = parse_match_answer(match[0]["answer"])
    assert re.search(rf"1\s*-\s*{key[1].lower()}\s*,\s*2\s*-\s*{key[2].lower()}", flat), flat
    # a Match key is not run through the Diagram/Equation/Explanation marks split
    assert "Marks split" not in flat


# --- blueprint papers --------------------------------------------------------


async def test_blueprint_sections_can_use_the_new_types(client):
    body = {
        "title": "Term test",
        "subject": "Science",
        "grade": 8,
        "chapters": [{"name": "Photosynthesis", "weightage": 60}, {"name": "Respiration", "weightage": 40}],
        "sections": [
            {"name": "Section A", "type": "Fill", "marks_per_question": 1, "total_marks": 5},
            {"name": "Section B", "type": "Match", "marks_per_question": 3, "total_marks": 6},
        ],
    }
    response = await client.post("/papers/blueprint", json=body)
    assert response.status_code == 201, response.text
    items = response.json()["questions"]
    assert response.json()["total_marks"] == 11
    assert [i["section"] for i in items] == ["Section A"] * 5 + ["Section B"] * 2
    assert {i["question"]["type"] for i in items[:5]} == {"Fill"}
    assert {i["question"]["type"] for i in items[5:]} == {"Match"}


@pytest.mark.parametrize(
    "q_type,marks", [("Fill", 2), ("Fill", 4), ("MCQ", 2), ("Match", 2), ("Match", 4), ("Long", 2)]
)
async def test_blueprint_rejects_marks_the_type_does_not_support(client, groq_stub, q_type, marks):
    body = {
        "title": "Bad", "subject": "Science", "grade": 8,
        "chapters": [{"name": "Photosynthesis", "weightage": 100}],
        "sections": [{"name": "A", "type": q_type, "marks_per_question": marks, "total_marks": 12}],
    }
    response = await client.post("/papers/blueprint", json=body)
    assert response.status_code in (400, 422)
    assert groq_stub.calls == []


# --- the database enum -------------------------------------------------------


async def test_migration_0009_is_the_head_and_applies_cleanly(tmp_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"}
    run = lambda *args: subprocess.run(  # noqa: E731
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True,
    )
    heads = run("heads")
    assert heads.returncode == 0, heads.stderr
    assert "0009" in heads.stdout
    up = run("upgrade", "head")
    assert up.returncode == 0, up.stderr
    # and back: a downgrade past 0009 is a harmless no-op, not an error
    down = run("downgrade", "0008")
    assert down.returncode == 0, down.stderr


async def test_orm_enum_accepts_the_new_values(db_session):
    from app.models import Question

    allowed = set(Question.__table__.c.type.type.enums)
    assert {"MCQ", "Short", "Long", "Fill", "Match"} <= allowed


async def test_exports_print_questions_in_ascending_order_of_marks(client, db_session, monkeypatch):
    """The paper was built Fill, Match, MCQ (1, 1, 3, 3, 1 marks); every export prints 1, 1, 1, 3, 3."""
    from app.services.export.fpdf_renderer import fpdf_available
    from .test_export_rendering import _pdf_text

    paper, _ = await _mixed_paper(client, db_session)
    assert [i.effective_marks for i in sorted(paper.items, key=lambda i: i.order_index)] == [1, 1, 3, 3, 1]

    html = html_service.render_paper_html(paper, include_answer_key=False)
    assert [int(m) for m in re.findall(r"class='q-marks'>\[(\d+)\]", html)] == [1, 1, 1, 3, 3]

    choices = ["reportlab"] + (["fpdf"] if fpdf_available() else [])
    for choice in choices:
        monkeypatch.setattr(renderer_service.settings, "pdf_renderer", choice)
        monkeypatch.setattr(renderer_service, "weasyprint_available", lambda: False)
        text = _pdf_text(renderer_service.render_pdf(paper, include_answer_key=False))
        assert [int(m) for m in re.findall(r"\[(\d+)\]", text)] == [1, 1, 1, 3, 3], choice
