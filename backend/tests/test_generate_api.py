"""
POST /generate — test-plan.md Section 1 (the rows that are Module B's
responsibility) and Section 2's `/generate` row.

Module A's own generation tests live in tests/test_engine.py at the repo
root; these check the HTTP surface: status codes, the error envelope,
persistence, and the caching layer.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

BASE = {
    "subject": "Science",
    "chapter": "Photosynthesis",
    "type": "Short",
    "grade": 8,
    "marks": 3,
    "difficulty": "medium",
    "count": 3,
}


async def test_generate_returns_requested_count(client):
    response = await client.post("/generate", json=BASE)
    assert response.status_code == 200, response.text

    body = response.json()
    assert len(body["questions"]) == 3
    assert body["generated"] == 3
    assert body["cached"] == 0


async def test_generated_questions_match_the_shared_contract(client):
    response = await client.post("/generate", json=BASE)
    question = response.json()["questions"][0]

    assert set(question) == {
        "id", "subject", "chapter", "type", "grade", "text", "options",
        "answer", "explanation", "marks", "difficulty", "topic", "tags",
    }
    assert question["subject"] == "Science"
    assert question["chapter"] == "Photosynthesis"
    assert question["type"] == "Short"
    assert question["grade"] == 8
    assert question["marks"] == 3
    assert question["difficulty"] == "medium"


async def test_generated_questions_are_persisted(client):
    await client.post("/generate", json=BASE)

    listing = await client.get("/questions", params={"subject": "Science"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 3


async def test_mcq_generation_returns_four_options(client):
    response = await client.post(
        "/generate", json={**BASE, "type": "MCQ", "marks": 1, "count": 2}
    )
    assert response.status_code == 200

    for question in response.json()["questions"]:
        assert question["type"] == "MCQ"
        assert len(question["options"]) == 4
        assert question["answer"] in question["options"]
        assert question["explanation"]


async def test_descriptive_questions_carry_no_options(client):
    response = await client.post("/generate", json={**BASE, "type": "Long", "marks": 5})
    for question in response.json()["questions"]:
        assert question["options"] is None


async def test_no_duplicates_within_a_batch(client):
    response = await client.post("/generate", json={**BASE, "count": 5})
    texts = [q["text"] for q in response.json()["questions"]]
    assert len(set(texts)) == len(texts)


# --- caching ---------------------------------------------------------------


async def test_repeat_request_is_served_from_cache(client, groq_stub):
    await client.post("/generate", json=BASE)
    calls_after_first = len(groq_stub.calls)

    second = await client.post("/generate", json=BASE)
    body = second.json()

    assert body["cached"] == 3
    assert body["generated"] == 0
    # The whole point: no additional Groq call.
    assert len(groq_stub.calls) == calls_after_first


async def test_refresh_flag_forces_fresh_generation(client, groq_stub):
    await client.post("/generate", json=BASE)
    calls_after_first = len(groq_stub.calls)

    second = await client.post("/generate", json={**BASE, "refresh": True})
    assert second.json()["generated"] == 3
    assert len(groq_stub.calls) > calls_after_first


async def test_cache_only_covers_the_shortfall(client, groq_stub):
    await client.post("/generate", json={**BASE, "count": 2})

    larger = await client.post("/generate", json={**BASE, "count": 5})
    body = larger.json()

    assert body["cached"] == 2
    assert body["generated"] == 3
    assert len(body["questions"]) == 5


async def test_cache_does_not_cross_difficulty(client):
    await client.post("/generate", json=BASE)
    other = await client.post("/generate", json={**BASE, "difficulty": "hard"})
    assert other.json()["cached"] == 0


# --- error paths -----------------------------------------------------------


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"type": "MCQ", "marks": 3}, "MCQ is fixed at 1 mark"),
        ({"type": "Long", "marks": 2}, "Long answers are 5-mark only"),
        ({"marks": 4}, "4 is not a valid mark value"),
        ({"grade": 11}, "grades are 7-9"),
        ({"subject": "Physics"}, "not one of the five subjects"),
        ({"chapter": "   "}, "chapter must not be blank"),
        ({"count": 0}, "count must be at least 1"),
    ],
)
async def test_invalid_combinations_return_400(client, override, reason):
    response = await client.post("/generate", json={**BASE, **override})
    assert response.status_code == 400, f"{reason}: {response.text}"
    assert set(response.json()) == {"error", "detail"}


async def test_invalid_request_stores_nothing(client):
    await client.post("/generate", json={**BASE, "marks": 4})
    listing = await client.get("/questions")
    assert listing.json()["total"] == 0


async def test_groq_failure_returns_502(failing_client):
    response = await failing_client.post("/generate", json=BASE)
    assert response.status_code == 502
    assert response.json()["error"] == "groq_api_error"


async def test_groq_failure_stores_nothing(failing_client):
    await failing_client.post("/generate", json=BASE)
    listing = await failing_client.get("/questions")
    assert listing.json()["total"] == 0


async def test_unusable_output_returns_422(bad_payload_client):
    response = await bad_payload_client.post("/generate", json=BASE)
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"


async def test_unusable_output_stores_nothing(bad_payload_client):
    await bad_payload_client.post("/generate", json=BASE)
    listing = await bad_payload_client.get("/questions")
    assert listing.json()["total"] == 0


async def test_count_ceiling_is_enforced(client):
    # MAX_BATCH_COUNT defaults to 25 (generation_engine/config.py).
    response = await client.post("/generate", json={**BASE, "count": 26})
    assert response.status_code == 400
