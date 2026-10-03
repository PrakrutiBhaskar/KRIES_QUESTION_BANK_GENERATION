"""
Figure-based generation over HTTP: figure metadata (subject, chapter, topic,
labelled parts), the library lookup behind `use_figures`, and the questions that
come back with their figure attached.

The Groq call is the stub from conftest.py; it follows the figure rules in the
prompt (one figure per question, spread round-robin, text pointing at it).
"""
from __future__ import annotations

import json

import pytest

from app.config import settings

from .test_figures import make_png, upload

pytestmark = pytest.mark.asyncio

BASE = {
    "subject": "Science",
    "chapter": "Photosynthesis",
    "type": "Short",
    "grade": 8,
    "marks": 2,
    "difficulty": "medium",
    "count": 4,
}

CELL_LABELS = "A: nucleus\nB: cell wall\nC: chloroplast"


async def add_figure(c, *, caption="Plant cell", subject="Science", chapter="Photosynthesis",
                     topic="", labels=CELL_LABELS, **kw) -> dict:
    r = await c.post(
        "/figures",
        files={"file": ("fig.png", make_png(), "image/png")},
        data={"caption": caption, "subject": subject, "chapter": chapter,
              "topic": topic, "labels": labels, **kw},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def generate(c, **overrides):
    return await c.post("/generate", json={**BASE, **overrides})


def figure_ids_of(response) -> list[str]:
    return [q["figure"]["id"] for q in response.json()["questions"]]


# --- figure metadata -----------------------------------------------------


async def test_upload_stores_and_returns_the_metadata(client, admin_client):
    fig = await add_figure(admin_client, subject="science", chapter="  Photosynthesis ",
                           topic=" Cell  structure ", labels="A: nucleus\n\n b: Cell wall \nA: NUCLEUS")
    assert fig["subject"] == "Science"           # canonical spelling
    assert fig["chapter"] == "Photosynthesis"
    assert fig["topic"] == "Cell structure"
    assert fig["labels"] == ["A: nucleus", "b: Cell wall"]  # tidied, repeats dropped


async def test_labels_can_be_sent_as_a_json_array(client, admin_client):
    fig = await add_figure(admin_client, labels=json.dumps(["1: root", "2: stem"]))
    assert fig["labels"] == ["1: root", "2: stem"]


async def test_a_figure_without_metadata_still_uploads(client, admin_client):
    r = await upload(admin_client, make_png(), caption="Just a picture")
    assert r.status_code == 201
    body = r.json()
    assert (body["subject"], body["chapter"], body["topic"], body["labels"]) == (None, None, "", [])


@pytest.mark.parametrize(
    "extra",
    [
        {"subject": "Astrology"},
        {"labels": "\n".join(f"{i}: part" for i in range(31))},
        {"labels": "x" * 81},
        {"labels": "[not json"},
        {"chapter": "c" * 121},
    ],
)
async def test_bad_metadata_is_a_400_and_nothing_is_stored(client, admin_client, extra):
    r = await admin_client.post(
        "/figures",
        files={"file": ("fig.png", make_png(), "image/png")},
        data={"caption": "x", **extra},
    )
    assert r.status_code == 400, r.text
    assert (await client.get("/figures")).json()["total"] == 0


async def test_patch_changes_only_what_is_sent_and_can_clear(client, admin_client):
    fig = await add_figure(admin_client, topic="Cells")
    r = await admin_client.patch(f"/figures/{fig['id']}", json={"labels": ["A: vacuole"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["labels"] == ["A: vacuole"]
    assert (body["caption"], body["subject"], body["chapter"], body["topic"]) == (
        "Plant cell", "Science", "Photosynthesis", "Cells")

    r = await admin_client.patch(f"/figures/{fig['id']}", json={"topic": "", "subject": None})
    body = r.json()
    assert body["topic"] == "" and body["subject"] is None
    assert body["chapter"] == "Photosynthesis"


async def test_an_empty_patch_is_rejected(client, admin_client):
    fig = await add_figure(admin_client)
    assert (await admin_client.patch(f"/figures/{fig['id']}", json={})).status_code == 400


async def test_a_bad_patch_changes_nothing(client, admin_client):
    fig = await add_figure(admin_client)
    r = await admin_client.patch(f"/figures/{fig['id']}", json={"caption": "new", "subject": "Astrology"})
    assert r.status_code == 400
    assert (await client.get(f"/figures/{fig['id']}")).json()["caption"] == "Plant cell"


async def test_labels_never_travel_with_a_question(client, admin_client):
    await add_figure(admin_client)
    r = await generate(client, use_figures=True)
    for q in r.json()["questions"]:
        assert set(q["figure"]) <= {"id", "caption", "mime", "width", "height", "size_bytes", "url", "created_at"}
    listing = await client.get("/questions", params={"subject": "Science"})
    for q in listing.json()["results"]:
        assert "labels" not in q["figure"]


async def test_list_can_be_filtered_by_subject_and_chapter(client, admin_client):
    await add_figure(admin_client, chapter="Photosynthesis")
    await add_figure(admin_client, chapter="Respiration")
    await add_figure(admin_client, subject="Math", chapter="Triangles")
    assert (await client.get("/figures")).json()["total"] == 3
    r = await client.get("/figures", params={"subject": "Science", "chapter": "photosynthesis"})
    assert r.json()["total"] == 1
    assert (await client.get("/figures", params={"subject": "Nope"})).status_code == 400


async def test_teachers_see_the_metadata_but_students_do_not(admin_client, client, session_factory):
    from httpx import ASGITransport, AsyncClient
    from app.main import app as fastapi_app

    fig = await add_figure(admin_client)
    for who in (admin_client, client):
        shown = (await who.get(f"/figures/{fig['id']}")).json()
        assert shown["labels"] == ["A: nucleus", "B: cell wall", "C: chloroplast"]
        assert (shown["subject"], shown["chapter"]) == ("Science", "Photosynthesis")

    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as student:
        r = await student.post(
            "/auth/signup",
            json={"name": "Stu Dent", "email": "stu@school.test", "password": "Passw0rd-test", "role": "Student"},
        )
        assert r.status_code == 201
        student.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        seen = (await student.get(f"/figures/{fig['id']}")).json()
        assert seen["caption"] == "Plant cell"          # image info is shared
        assert seen["labels"] == [] and seen["subject"] is None and seen["chapter"] is None
        listed = (await student.get("/figures")).json()["results"][0]
        assert listed["labels"] == []


async def test_a_teacher_generates_from_figures_an_admin_added(admin_client, client):
    """The library is shared: no per-user copies, no need to upload anything yourself."""
    fig = await add_figure(admin_client)
    r = await generate(client, use_figures=True)
    assert r.status_code == 200, r.text
    assert set(figure_ids_of(r)) == {fig["id"]}


async def test_every_teacher_draws_on_the_same_library(admin_client, client, bob_client):
    fig = await add_figure(admin_client)
    for teacher in (client, bob_client):
        r = await generate(teacher, use_figures=True, refresh=True)
        assert r.status_code == 200 and set(figure_ids_of(r)) == {fig["id"]}


async def test_naming_a_library_figure_works_for_any_teacher_and_a_missing_one_is_a_404(admin_client, client, bob_client):
    fig = await add_figure(admin_client)
    assert (await generate(bob_client, figure_ids=[fig["id"]])).status_code == 200
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await generate(client, figure_ids=[missing])).status_code == 404


async def test_teachers_cannot_add_figures_to_generate_from(client):
    r = await client.post(
        "/figures",
        files={"file": ("fig.png", make_png(), "image/png")},
        data={"caption": "mine", "subject": "Science", "chapter": "Photosynthesis"},
    )
    assert r.status_code == 403
    r = await generate(client, use_figures=True)
    assert r.status_code == 400 and r.json()["error"] == "no_figures"
    assert "administrator" in r.json()["detail"]


# --- generating with figures --------------------------------------------


async def test_use_figures_attaches_a_library_figure_to_every_question(client, admin_client, groq_stub):
    a = await add_figure(admin_client, caption="Plant cell")
    b = await add_figure(admin_client, caption="Leaf cross-section", labels="1: cuticle\n2: palisade layer")
    r = await generate(client, use_figures=True)
    assert r.status_code == 200, r.text
    ids = figure_ids_of(r)
    assert len(ids) == 4 and set(ids) == {a["id"], b["id"]}   # spread over both
    assert all("figure" in q for q in r.json()["questions"])

    # The model got the metadata as text, and never the real ids.
    prompt = groq_stub.generation_calls[0][1]
    assert "Caption: Plant cell" in prompt
    assert "Labelled parts: A: nucleus; B: cell wall; C: chloroplast" in prompt
    assert "Labelled parts: 1: cuticle; 2: palisade layer" in prompt
    assert a["id"] not in prompt and b["id"] not in prompt


async def test_the_figure_is_stored_with_the_question(client, admin_client):
    fig = await add_figure(admin_client)
    await generate(client, use_figures=True, count=2)
    listing = await client.get("/questions", params={"subject": "Science"})
    assert [q["figure"]["id"] for q in listing.json()["results"]] == [fig["id"]] * 2


async def test_questions_come_back_after_the_figure_check_with_a_clean_report(client, admin_client):
    await add_figure(admin_client)
    report = (await generate(client, use_figures=True)).json()["report"]
    assert report["dropped_figure_invalid"] == 0


async def test_no_figures_for_the_chapter_is_a_400_that_says_so(client, admin_client, groq_stub):
    await add_figure(admin_client, chapter="Respiration")      # a different chapter
    r = await generate(client, use_figures=True)
    assert r.status_code == 400
    assert r.json()["error"] == "no_figures"
    assert "Photosynthesis" in r.json()["detail"]
    assert groq_stub.calls == []                         # no Groq call was spent


async def test_a_figure_with_nothing_to_write_from_is_not_used(client, admin_client):
    await add_figure(admin_client, caption="", labels="")
    r = await generate(client, use_figures=True)
    assert r.status_code == 400 and r.json()["error"] == "no_figures"


async def test_a_caption_alone_is_enough(client, admin_client):
    await add_figure(admin_client, caption="The water cycle", labels="")
    assert (await generate(client, use_figures=True)).status_code == 200


async def test_untagged_figures_are_not_picked_automatically(client, admin_client):
    await upload(admin_client, make_png(), caption="Untagged")
    r = await generate(client, use_figures=True)
    assert r.status_code == 400 and r.json()["error"] == "no_figures"


async def test_the_topic_narrows_the_figures(client, admin_client, groq_stub):
    await add_figure(admin_client, caption="Cell figure", topic="Cells")
    await add_figure(admin_client, caption="Leaf figure", topic="Leaves")
    await add_figure(admin_client, caption="Chapter-wide figure", topic="")
    await generate(client, use_figures=True, topic="Cells", count=2)
    prompt = groq_stub.generation_calls[0][1]
    assert "Cell figure" in prompt and "Chapter-wide figure" in prompt
    assert "Leaf figure" not in prompt


async def test_chapter_matching_ignores_case(client, admin_client):
    await add_figure(admin_client, chapter="photosynthesis")
    assert (await generate(client, use_figures=True)).status_code == 200


async def test_named_figures_are_used_exactly_and_imply_use_figures(client, admin_client, groq_stub):
    a = await add_figure(admin_client, caption="Figure A")
    await add_figure(admin_client, caption="Figure B")
    r = await generate(client, figure_ids=[a["id"]])
    assert r.status_code == 200, r.text
    assert set(figure_ids_of(r)) == {a["id"]}
    prompt = groq_stub.generation_calls[0][1]
    assert "Figure A" in prompt and "Figure B" not in prompt


async def test_named_figures_need_not_be_tagged_with_the_chapter(client, admin_client):
    fig = await add_figure(admin_client, chapter="Respiration")
    assert (await generate(client, figure_ids=[fig["id"]])).status_code == 200


async def test_a_named_figure_without_metadata_is_a_clear_400(client, admin_client):
    fig = await add_figure(admin_client, caption="", labels="")
    r = await generate(client, figure_ids=[fig["id"]])
    assert r.status_code == 400 and r.json()["error"] == "figure_has_no_metadata"


async def test_figure_ids_are_validated(client, admin_client):
    fig = await add_figure(admin_client)
    # validation errors are 400 in this API (api-contract.md), not FastAPI's 422
    assert (await generate(client, figure_ids=[fig["id"], fig["id"]])).status_code == 400
    assert (await generate(client, figure_ids=[])).status_code == 400


async def test_too_many_named_figures_is_a_400(client, admin_client, monkeypatch):
    monkeypatch.setattr(settings, "max_generation_figures", 2)
    figs = [await add_figure(admin_client, caption=f"Fig {i}") for i in range(3)]
    r = await generate(client, figure_ids=[f["id"] for f in figs])
    assert r.status_code == 400 and r.json()["error"] == "too_many_figures"


async def test_the_library_is_capped_and_rotates_to_the_least_used(client, admin_client, monkeypatch, groq_stub):
    monkeypatch.setattr(settings, "max_generation_figures", 1)
    a = await add_figure(admin_client, caption="Figure A")
    b = await add_figure(admin_client, caption="Figure B")
    # Use A twice, explicitly...
    await generate(client, figure_ids=[a["id"]], count=2)
    # ...then let the library choose: with room for one, B (used 0 times) wins.
    r = await generate(client, use_figures=True, count=2, refresh=True)
    assert set(figure_ids_of(r)) == {b["id"]}


# --- caching ----------------------------------------------------------------


async def test_a_repeat_figure_request_is_served_from_storage(client, admin_client, groq_stub):
    await add_figure(admin_client)
    first = await generate(client, use_figures=True)
    calls = len(groq_stub.generation_calls)
    again = await generate(client, use_figures=True)
    body = again.json()
    assert (body["cached"], body["generated"]) == (4, 0)
    assert len(groq_stub.generation_calls) == calls
    assert [q["id"] for q in body["questions"]] and {q["id"] for q in body["questions"]} == {
        q["id"] for q in first.json()["questions"]}


async def test_refresh_makes_new_figure_questions(client, admin_client):
    await add_figure(admin_client)
    first = await generate(client, use_figures=True)
    more = await generate(client, use_figures=True, refresh=True)
    assert {q["id"] for q in more.json()["questions"]}.isdisjoint(
        {q["id"] for q in first.json()["questions"]})


async def test_plain_questions_are_not_reused_for_a_figure_request(client, admin_client):
    await add_figure(admin_client)
    await generate(client)                       # 4 plain questions are now stored
    r = await generate(client, use_figures=True)
    body = r.json()
    assert (body["cached"], body["generated"]) == (0, 4)
    assert all("figure" in q for q in body["questions"])


async def test_a_plain_request_is_unchanged(client, admin_client):
    await add_figure(admin_client)
    r = await generate(client)
    assert all("figure" not in q for q in r.json()["questions"])


# --- verification sees the figure ---------------------------------------------


async def test_the_answer_verifier_is_told_what_the_figure_shows(client, admin_client, groq_stub, monkeypatch):
    from generation_engine import engine as engine_module
    import dataclasses
    monkeypatch.setattr(
        engine_module, "settings",
        dataclasses.replace(engine_module.settings, enable_llm_answer_verification=True),
    )
    await add_figure(admin_client)
    r = await generate(client, use_figures=True, count=2)
    assert r.status_code == 200, r.text
    verifier_prompt = groq_stub.verification_calls[0][1]
    assert '"figure": "Caption: Plant cell' in verifier_prompt
    assert "A: nucleus" in verifier_prompt
