"""Rate limiting: the limiter itself, the middleware, and the login lockout."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, parse_rule, settings
from app.ratelimit import Rule, SlidingWindowLimiter, limiter

GENERATE = {
    "subject": "Science",
    "chapter": "Photosynthesis",
    "type": "MCQ",
    "grade": 8,
    "marks": 1,
    "difficulty": "easy",
    "count": 1,
}


@pytest.fixture
def limits(monkeypatch):
    """Turn rate limiting on; tests then override individual limits."""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    def set_(**values):
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)

    return set_


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock for the shared limiter."""
    now = [1000.0]
    monkeypatch.setattr(limiter, "_clock", lambda: now[0])
    return now


def _login(c, email="alice@school.test", password="Passw0rd-test"):
    return c.post("/auth/login", json={"email": email, "password": password})


# --- config parsing -------------------------------------------------------------


def test_parse_rule():
    assert parse_rule("10/60") == Rule(10, 60.0)
    assert parse_rule(" 5/3600 ") == Rule(5, 3600.0)


@pytest.mark.parametrize("bad", ["", "10", "a/b", "10/60/1", "0/60", "-1/60", "10/0", "10/-5"])
def test_parse_rule_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        parse_rule(bad)


def test_bad_limit_in_settings_fails_at_startup_with_a_clear_message():
    with pytest.raises(ValidationError, match="expected '<requests>/<seconds>'"):
        Settings(RATE_LIMIT_LOGIN="lots")


# --- the limiter ----------------------------------------------------------------


def test_limiter_allows_up_to_the_limit_then_blocks_until_the_window_passes():
    t = [0.0]
    lim = SlidingWindowLimiter(clock=lambda: t[0])
    rule = Rule(3, 60)

    assert [lim.hit("k", rule) for _ in range(3)] == [0.0, 0.0, 0.0]
    wait = lim.hit("k", rule)
    assert wait == pytest.approx(60)

    t[0] = 30
    assert lim.hit("k", rule) == pytest.approx(30)  # counted from the *first* hit
    t[0] = 60.5
    assert lim.hit("k", rule) == 0.0  # oldest hit has aged out


def test_rejected_attempts_do_not_extend_the_penalty():
    t = [0.0]
    lim = SlidingWindowLimiter(clock=lambda: t[0])
    rule = Rule(1, 10)
    assert lim.hit("k", rule) == 0.0
    for t[0] in (1, 2, 3, 4, 5):
        assert lim.hit("k", rule) > 0
    t[0] = 10.1
    assert lim.hit("k", rule) == 0.0


def test_limiter_keys_are_independent_and_clearable():
    lim = SlidingWindowLimiter(clock=lambda: 0.0)
    rule = Rule(1, 60)
    assert lim.hit("a", rule) == 0.0
    assert lim.hit("b", rule) == 0.0
    assert lim.hit("a", rule) > 0
    lim.clear("a")
    assert lim.hit("a", rule) == 0.0


def test_limiter_peek_and_record_do_not_interfere():
    lim = SlidingWindowLimiter(clock=lambda: 0.0)
    rule = Rule(2, 60)
    assert lim.retry_after("k", rule) == 0.0
    lim.record("k", rule)
    assert lim.retry_after("k", rule) == 0.0
    lim.record("k", rule)
    assert lim.retry_after("k", rule) > 0


def test_limiter_forgets_idle_keys():
    t = [0.0]
    lim = SlidingWindowLimiter(clock=lambda: t[0])
    for i in range(50):
        lim.hit(f"user-{i}", Rule(5, 10))
    t[0] = 1000.0
    for _ in range(SlidingWindowLimiter._SWEEP_EVERY):
        lim.retry_after("busy", Rule(5, 10))
    assert len(lim._hits) <= 2  # the 50 idle keys were purged


# --- middleware: the 429 response --------------------------------------------------


async def test_login_is_limited_per_ip_and_the_429_is_well_formed(anon_client, limits):
    limits(rate_limit_login="3/60")
    for _ in range(3):
        assert (await _login(anon_client, password="wrong-Pass1")).status_code == 401

    r = await anon_client.post(
        "/auth/login",
        json={"email": "alice@school.test", "password": "x"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited"
    assert "Try again in" in r.json()["detail"]
    assert 1 <= int(r.headers["retry-after"]) <= 60
    # CORS headers must be on the 429, or the browser hides it as a network error.
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_signup_is_limited_per_ip(anon_client, limits):
    limits(rate_limit_signup="2/3600")
    for i in range(2):
        r = await anon_client.post(
            "/auth/signup",
            json={"name": "N", "email": f"n{i}@school.test", "password": "Passw0rd-test"},
        )
        assert r.status_code == 201
    r = await anon_client.post(
        "/auth/signup",
        json={"name": "N", "email": "n3@school.test", "password": "Passw0rd-test"},
    )
    assert r.status_code == 429


async def test_generation_is_limited_per_user(client, bob_client, limits):
    limits(rate_limit_generate="2/60")
    for _ in range(2):
        assert (await client.post("/generate", json=GENERATE)).status_code == 200
    assert (await client.post("/generate", json=GENERATE)).status_code == 429

    # Other endpoints and other users are unaffected.
    assert (await client.get("/questions")).status_code == 200
    assert (await bob_client.post("/generate", json=GENERATE)).status_code == 200


async def test_practice_sessions_share_the_generation_limit(client, limits):
    limits(rate_limit_generate="1/60")
    body = {"subject": "Science", "chapter": "Photosynthesis", "type": "MCQ", "grade": 8, "count": 1}
    assert (await client.post("/practice/sessions", json=body)).status_code == 201
    assert (await client.post("/generate", json=GENERATE)).status_code == 429


async def test_blueprint_papers_share_the_generation_limit_but_previews_do_not(client, limits):
    """A blueprint paper can make many LLM calls, so it counts against the same
    per-user budget as /generate. The preview does no LLM work and is exempt."""
    from .test_blueprint import blueprint

    limits(rate_limit_generate="1/60")
    for _ in range(3):
        assert (await client.post("/papers/blueprint/preview", json=blueprint())).status_code == 200

    assert (await client.post("/papers/blueprint", json=blueprint())).status_code == 201
    assert (await client.post("/papers/blueprint", json=blueprint())).status_code == 429
    assert (await client.post("/generate", json=GENERATE)).status_code == 429


async def test_export_is_limited_per_user_but_downloads_are_not(client, limits):
    qs = (await client.post("/generate", json={**GENERATE, "count": 1})).json()["questions"]
    paper = (
        await client.post(
            "/papers", json={"title": "P", "subject": "Science", "question_ids": [qs[0]["id"]]}
        )
    ).json()
    limits(rate_limit_export="2/60")

    first = await client.post(f"/export/{paper['id']}")
    assert first.status_code == 200
    assert (await client.post(f"/export/{paper['id']}")).status_code == 200
    assert (await client.post(f"/export/{paper['id']}")).status_code == 429

    # Fetching a file that was already exported still works.
    url = first.json()["download_url"].split("/api/v1", 1)[1]
    assert (await client.get(url)).status_code == 200


async def test_global_limit_covers_every_route_but_not_health_or_preflight(client, limits):
    limits(rate_limit_default="5/60")
    for _ in range(5):
        assert (await client.get("/subjects")).status_code == 200
    assert (await client.get("/subjects")).status_code == 429
    assert (await client.get("/papers")).status_code == 429  # same bucket

    assert (await client.get("http://test/health")).status_code == 200
    pre = await client.options(
        "/subjects",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert pre.status_code != 429


async def test_unknown_paths_are_limited_too(anon_client, limits):
    limits(rate_limit_default="3/60")
    for _ in range(3):
        assert (await anon_client.get("/no-such-route")).status_code == 404
    assert (await anon_client.get("/no-such-route")).status_code == 429


async def test_anonymous_callers_are_limited_by_ip_and_fake_tokens_dont_help(anon_client, limits):
    limits(rate_limit_default="4/60")
    statuses = []
    for i in range(6):
        r = await anon_client.get("/papers", headers={"Authorization": f"Bearer forged-{i}"})
        statuses.append(r.status_code)
    assert statuses == [401, 401, 401, 401, 429, 429]


async def test_forwarded_for_is_ignored_unless_proxy_headers_are_trusted(anon_client, limits):
    limits(rate_limit_default="2/60")
    codes = [
        (await anon_client.get("/papers", headers={"X-Forwarded-For": f"9.9.9.{i}"})).status_code
        for i in range(3)
    ]
    assert codes == [401, 401, 429]  # spoofed IPs all landed in one bucket


async def test_forwarded_for_is_used_behind_a_trusted_proxy(anon_client, limits):
    limits(rate_limit_default="1/60", trust_proxy_headers=True)
    a = await anon_client.get("/papers", headers={"X-Forwarded-For": "9.9.9.1, 10.0.0.1"})
    b = await anon_client.get("/papers", headers={"X-Forwarded-For": "9.9.9.2"})
    again = await anon_client.get("/papers", headers={"X-Forwarded-For": "9.9.9.1"})
    assert (a.status_code, b.status_code, again.status_code) == (401, 401, 429)


async def test_nothing_is_limited_when_disabled(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_default", "1/60")
    for _ in range(5):
        assert (await anon_client.get("/papers")).status_code == 401


# --- failed-login lockout --------------------------------------------------------


async def test_repeated_wrong_passwords_lock_out_that_email_from_that_ip(anon_client, limits):
    limits(rate_limit_login="100/60", login_max_failures="3/900")
    await anon_client.post(
        "/auth/signup", json={"name": "A", "email": "alice@school.test", "password": "Passw0rd-test"}
    )
    for _ in range(3):
        assert (await _login(anon_client, password="wrong-Pass1")).status_code == 401

    locked = await _login(anon_client, password="wrong-Pass1")
    assert locked.status_code == 429
    assert "failed sign-in attempts" in locked.json()["detail"]
    assert "retry-after" in locked.headers

    # Even the right password is refused while locked, or guessing would just continue.
    assert (await _login(anon_client)).status_code == 429
    # A different account from the same IP is not affected.
    assert (await _login(anon_client, email="other@school.test", password="x")).status_code == 401


async def test_lockout_lifts_after_the_window(anon_client, limits, clock):
    limits(rate_limit_login="100/60", login_max_failures="2/900")
    await anon_client.post(
        "/auth/signup", json={"name": "A", "email": "alice@school.test", "password": "Passw0rd-test"}
    )
    for _ in range(2):
        await _login(anon_client, password="wrong-Pass1")
    assert (await _login(anon_client)).status_code == 429

    clock[0] += 901
    assert (await _login(anon_client)).status_code == 200


async def test_a_successful_login_resets_the_failure_count(anon_client, limits):
    limits(rate_limit_login="100/60", login_max_failures="3/900")
    await anon_client.post(
        "/auth/signup", json={"name": "A", "email": "alice@school.test", "password": "Passw0rd-test"}
    )
    for _ in range(2):
        await _login(anon_client, password="wrong-Pass1")
    assert (await _login(anon_client)).status_code == 200
    for _ in range(2):  # would have been the 3rd and 4th failure without the reset
        assert (await _login(anon_client, password="wrong-Pass1")).status_code == 401
