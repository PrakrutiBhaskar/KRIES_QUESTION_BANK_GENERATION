"""Access control and ownership: who may see or change what."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import update

from app import security
from app.config import settings
from app.models import Paper, Question

from .conftest import generate_questions

SESSION = {
    "subject": "Science",
    "chapter": "Photosynthesis",
    "type": "MCQ",
    "grade": 8,
    "difficulty": "easy",
    "count": 3,
}


async def _paper(c, title="Alice's paper"):
    qs = await generate_questions(c, count=2)
    r = await c.post(
        "/papers",
        json={"title": title, "subject": "Science", "question_ids": [q["id"] for q in qs]},
    )
    assert r.status_code == 201, r.text
    return r.json(), qs


# --- everything except sign-up / sign-in needs a token ------------------------

PROTECTED = [
    ("GET", "/questions"),
    ("GET", f"/questions/{uuid.uuid4()}"),
    ("PATCH", f"/questions/{uuid.uuid4()}"),
    ("DELETE", f"/questions/{uuid.uuid4()}"),
    ("POST", "/generate"),
    ("GET", "/generation/combinations"),
    ("GET", "/papers"),
    ("POST", "/papers"),
    ("GET", f"/papers/{uuid.uuid4()}"),
    ("PATCH", f"/papers/{uuid.uuid4()}"),
    ("DELETE", f"/papers/{uuid.uuid4()}"),
    ("POST", f"/export/{uuid.uuid4()}"),
    ("POST", "/practice/sessions"),
    ("GET", f"/practice/sessions/{uuid.uuid4()}"),
    ("GET", f"/practice/sessions/{uuid.uuid4()}/reveal/{uuid.uuid4()}"),
    ("GET", "/subjects"),
    ("GET", "/auth/me"),
    ("POST", "/figures"),
    ("GET", "/figures"),
    ("GET", f"/figures/{uuid.uuid4()}"),
    ("GET", f"/figures/{uuid.uuid4()}/file"),
    ("PATCH", f"/figures/{uuid.uuid4()}"),
    ("DELETE", f"/figures/{uuid.uuid4()}"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
async def test_protected_routes_reject_anonymous_callers(anon_client, method, path):
    r = await anon_client.request(method, path, json={} if method in ("POST", "PATCH") else None)
    assert r.status_code == 401, (method, path, r.status_code, r.text)
    assert r.json()["error"] in ("not_authenticated", "invalid_token")


async def test_signup_login_and_health_stay_public(anon_client):
    assert (await anon_client.post("/auth/login", json={"email": "a@b.co", "password": "x"})).status_code == 401
    r = await anon_client.post(
        "/auth/signup", json={"name": "New", "email": "new@school.test", "password": "Passw0rd-test"}
    )
    assert r.status_code == 201
    health = await anon_client.get("http://test/health")
    assert health.status_code == 200


# --- papers are private ---------------------------------------------------------


async def test_a_users_papers_are_invisible_to_others(client, bob_client):
    paper, _ = await _paper(client)

    assert [p["id"] for p in (await client.get("/papers")).json()] == [paper["id"]]
    assert (await bob_client.get("/papers")).json() == []


async def test_other_users_cannot_read_change_export_or_delete_a_paper(client, bob_client):
    paper, _ = await _paper(client)
    pid = paper["id"]

    assert (await bob_client.get(f"/papers/{pid}")).status_code == 404
    assert (await bob_client.patch(f"/papers/{pid}", json={"title": "hijacked"})).status_code == 404
    assert (await bob_client.post(f"/export/{pid}")).status_code == 404
    assert (await bob_client.delete(f"/papers/{pid}")).status_code == 404

    # ...and none of it touched the real thing.
    mine = (await client.get(f"/papers/{pid}")).json()
    assert mine["title"] == "Alice's paper"


async def test_foreign_paper_looks_exactly_like_a_missing_one(client, bob_client):
    paper, _ = await _paper(client)
    foreign = await bob_client.get(f"/papers/{paper['id']}")
    missing = await bob_client.get(f"/papers/{uuid.uuid4()}")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"] == missing.json()["error"]


async def test_new_papers_are_owned_by_the_caller_not_by_the_request(client, bob_client):
    qs = await generate_questions(client, count=1)
    r = await bob_client.post(
        "/papers",
        json={"title": "Bob's", "subject": "Science", "question_ids": [qs[0]["id"]]},
    )
    assert r.status_code == 201
    bob_id = (await bob_client.get("/auth/me")).json()["id"]
    assert r.json()["user_id"] == bob_id

    # Trying to assign ownership through the body is rejected outright.
    r = await bob_client.post(
        "/papers",
        json={
            "title": "x",
            "subject": "Science",
            "question_ids": [qs[0]["id"]],
            "user_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 400


async def test_papers_created_before_sign_in_existed_stay_hidden(client, db_session):
    paper, _ = await _paper(client)
    await db_session.execute(update(Paper).values(user_id=None))
    await db_session.commit()

    assert (await client.get("/papers")).json() == []
    assert (await client.get(f"/papers/{paper['id']}")).status_code == 404


# --- the question pool is shared, but only the creator can change it -----------


async def test_questions_are_readable_by_any_signed_in_user(client, bob_client):
    [q] = await generate_questions(client, count=1)
    assert (await bob_client.get(f"/questions/{q['id']}")).status_code == 200
    assert (await bob_client.get("/questions")).json()["total"] >= 1


async def test_a_second_user_reuses_cached_questions_from_the_shared_pool(client, bob_client):
    mine = await generate_questions(client, count=2)
    theirs = await generate_questions(bob_client, count=2)
    assert {q["id"] for q in mine} == {q["id"] for q in theirs}


async def test_only_the_creator_can_edit_a_question(client, bob_client):
    [q] = await generate_questions(client, count=1)
    body = {"topic": "edited-topic"}

    r = await bob_client.patch(f"/questions/{q['id']}", json=body)
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden"
    assert (await client.get(f"/questions/{q['id']}")).json()["topic"] != "edited-topic"

    assert (await client.patch(f"/questions/{q['id']}", json=body)).status_code == 200


async def test_discarding_someone_elses_question_changes_nothing(client, bob_client):
    [q] = await generate_questions(client, count=1)

    # Bob's draft can drop it (204), but it stays in the pool for everyone.
    assert (await bob_client.delete(f"/questions/{q['id']}")).status_code == 204
    assert (await client.get(f"/questions/{q['id']}")).status_code == 200

    # The creator really can remove it.
    assert (await client.delete(f"/questions/{q['id']}")).status_code == 204
    assert (await client.get(f"/questions/{q['id']}")).status_code == 404


async def test_questions_from_before_sign_in_cannot_be_edited_or_removed(client, db_session):
    [q] = await generate_questions(client, count=1)
    await db_session.execute(update(Question).values(created_by=None))
    await db_session.commit()

    assert (await client.patch(f"/questions/{q['id']}", json={"topic": "x"})).status_code == 403
    assert (await client.delete(f"/questions/{q['id']}")).status_code == 204
    assert (await client.get(f"/questions/{q['id']}")).status_code == 200


async def test_papers_can_mix_in_questions_generated_by_others(client, bob_client):
    [q] = await generate_questions(client, count=1)
    r = await bob_client.post(
        "/papers", json={"title": "Reuse", "subject": "Science", "question_ids": [q["id"]]}
    )
    assert r.status_code == 201


# --- practice sessions are private --------------------------------------------


async def test_practice_sessions_belong_to_their_creator(client, bob_client):
    created = await client.post("/practice/sessions", json=SESSION)
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    qid = created.json()["questions"][0]["id"]

    assert (await client.get(f"/practice/sessions/{sid}")).status_code == 200
    assert (await client.get(f"/practice/sessions/{sid}/reveal/{qid}")).status_code == 200

    assert (await bob_client.get(f"/practice/sessions/{sid}")).status_code == 404
    assert (await bob_client.get(f"/practice/sessions/{sid}/reveal/{qid}")).status_code == 404


# --- download links -------------------------------------------------------------


async def _export(c):
    paper, _ = await _paper(c)
    body = (await c.post(f"/export/{paper['id']}")).json()
    token = body["download_url"].split("token=")[1]
    return body["filename"], token


async def test_download_needs_the_signed_link(client, anon_client):
    filename, token = await _export(client)

    # Works with no Authorization header (that's how a new browser tab opens it)...
    ok = await anon_client.get(f"/export/files/{filename}", params={"token": token})
    assert ok.status_code == 200 and ok.content.startswith(b"%PDF-")

    # ...but not without the token, even for a signed-in user.
    assert (await anon_client.get(f"/export/files/{filename}")).status_code == 401
    assert (await client.get(f"/export/files/{filename}")).status_code == 401
    assert (await anon_client.get(f"/export/files/{filename}", params={"token": "junk"})).status_code == 401


async def test_download_token_is_bound_to_one_file(client, anon_client):
    filename, token = await _export(client)
    other, _ = await _export(client)
    assert filename != other
    r = await anon_client.get(f"/export/files/{other}", params={"token": token})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_download_token"


async def test_download_token_expires(client, anon_client):
    filename, _ = await _export(client)
    expired = security.create_download_token(filename, ttl_seconds=-5)
    r = await anon_client.get(f"/export/files/{filename}", params={"token": expired})
    assert r.status_code == 401


async def test_download_and_access_tokens_are_not_interchangeable(client, anon_client):
    filename, download_token = await _export(client)
    access_token = client.headers["Authorization"].split(" ", 1)[1]

    # A sign-in token can't open a download...
    assert (await anon_client.get(f"/export/files/{filename}", params={"token": access_token})).status_code == 401
    # ...and a download token can't sign anyone in.
    r = await anon_client.get("/auth/me", headers={"Authorization": f"Bearer {download_token}"})
    assert r.status_code == 401


async def test_download_token_signed_with_another_key_is_rejected(client, anon_client):
    filename, _ = await _export(client)
    forged = jwt.encode(
        {"typ": "download", "fn": filename, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "an-attacker-chosen-secret-key-1234567890",
        algorithm=settings.jwt_algorithm,
    )
    assert (await anon_client.get(f"/export/files/{filename}", params={"token": forged})).status_code == 401
