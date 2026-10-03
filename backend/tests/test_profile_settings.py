"""PATCH /auth/me: the Settings page's profile and preference changes."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import User

DEFAULTS = {
    "theme": "light",
    "notifications": True,
    "default_question_count": 10,
    "default_difficulty": "mixed",
    "default_question_type": "Mixed",
    "default_marks": 2,
}


async def test_me_reports_default_preferences_for_a_new_account(client):
    body = (await client.get("/auth/me")).json()
    assert body["preferences"] == DEFAULTS


async def test_name_change_is_saved_and_visible_on_next_read(client):
    r = await client.patch("/auth/me", json={"name": "  Alice   B. Teacher "})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Alice B. Teacher"
    assert (await client.get("/auth/me")).json()["name"] == "Alice B. Teacher"


async def test_preferences_are_stored_in_the_database(client, db_session):
    prefs = {
        "theme": "dark",
        "notifications": False,
        "default_question_count": 15,
        "default_difficulty": "hard",
        "default_question_type": "MCQ",
        "default_marks": 5,
    }
    r = await client.patch("/auth/me", json={"preferences": prefs})
    assert r.status_code == 200, r.text
    assert r.json()["preferences"] == prefs

    user = (await db_session.execute(select(User).where(User.email == "alice@school.test"))).scalar_one()
    assert user.preferences == prefs


async def test_preferences_survive_signing_in_again(client, anon_client):
    await client.patch("/auth/me", json={"preferences": {"theme": "dark", "default_marks": 3}})
    login = await anon_client.post(
        "/auth/login", json={"email": "alice@school.test", "password": "Passw0rd-test"}
    )
    assert login.status_code == 200
    prefs = login.json()["user"]["preferences"]
    assert prefs["theme"] == "dark" and prefs["default_marks"] == 3


async def test_partial_preferences_leave_the_others_alone(client):
    await client.patch("/auth/me", json={"preferences": {"theme": "dark", "default_marks": 5}})
    r = await client.patch("/auth/me", json={"preferences": {"notifications": False}})
    prefs = r.json()["preferences"]
    assert prefs["theme"] == "dark" and prefs["default_marks"] == 5 and prefs["notifications"] is False


async def test_email_cannot_be_changed(client):
    r = await client.patch("/auth/me", json={"email": "new@school.test"})
    assert r.status_code == 403
    assert r.json()["error"] == "email_immutable"
    assert (await client.get("/auth/me")).json()["email"] == "alice@school.test"


async def test_email_rejection_applies_even_alongside_other_changes(client):
    r = await client.patch("/auth/me", json={"name": "Hacker", "email": "new@school.test"})
    assert r.status_code == 403
    assert (await client.get("/auth/me")).json()["name"] == "Alice Teacher"


async def test_role_can_switch_between_teacher_and_student(client):
    r = await client.patch("/auth/me", json={"role": "Student"})
    assert r.json()["role"] == "Student"


async def test_admin_cannot_be_self_assigned(client):
    r = await client.patch("/auth/me", json={"role": "Admin"})
    assert r.status_code == 400


async def test_admin_role_is_locked(client, db_session):
    user = (await db_session.execute(select(User))).scalar_one()
    user.role = "Admin"
    await db_session.commit()
    r = await client.patch("/auth/me", json={"role": "Teacher"})
    assert r.status_code == 403
    assert r.json()["error"] == "role_locked"
    # re-sending the same role is harmless
    assert (await client.patch("/auth/me", json={"role": "Teacher", "name": "Boss"})).status_code == 403
    assert (await client.patch("/auth/me", json={"name": "Boss"})).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"name": "   "},
        {"name": "x" * 101},
        {"preferences": {"theme": "neon"}},
        {"preferences": {"default_question_count": 2}},
        {"preferences": {"default_question_count": 31}},
        {"preferences": {"default_marks": 4}},
        {"preferences": {"default_difficulty": "impossible"}},
        {"preferences": {"default_question_type": "Essay"}},
        {"preferences": {"unknown_key": 1}},
        {"is_active": False},
        {"password": "NewPassw0rd"},
    ],
)
async def test_invalid_changes_are_rejected_and_nothing_is_saved(client, body):
    r = await client.patch("/auth/me", json=body)
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_request"
    me = (await client.get("/auth/me")).json()
    assert me["name"] == "Alice Teacher" and me["preferences"] == DEFAULTS


async def test_patch_requires_sign_in(anon_client):
    r = await anon_client.patch("/auth/me", json={"name": "Nobody"})
    assert r.status_code == 401


async def test_one_user_cannot_change_another(client, bob_client):
    await client.patch("/auth/me", json={"name": "Alice Changed", "preferences": {"theme": "dark"}})
    bob = (await bob_client.get("/auth/me")).json()
    assert bob["name"] == "Bob Teacher" and bob["preferences"]["theme"] == "light"
