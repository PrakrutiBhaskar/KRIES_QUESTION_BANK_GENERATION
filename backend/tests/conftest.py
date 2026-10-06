"""
Test fixtures for the backend suite.

Nothing here touches the network or a real database:
  * the DB is an in-memory SQLite bound to a single connection, so every
    session in a test sees the same data,
  * the Groq call is stubbed by `FakeGroqClient`, which returns well-formed
    question payloads — the same technique tests/test_engine.py uses for
    Module A.

The app's `get_session` dependency is overridden so routes and tests share
one transaction per test.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
for _p in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Set before app.config is imported: exported PDFs go to a scratch directory
# rather than the repo's var/exports.
os.environ.setdefault("EXPORT_DIR", tempfile.mkdtemp(prefix="qb-test-exports-"))
# Uploaded figures likewise go to a scratch directory.
os.environ.setdefault("FIGURE_DIR", tempfile.mkdtemp(prefix="qb-test-figures-"))
# Rate limits would trip over the many requests a test suite makes. The tests in
# test_rate_limiting.py switch them back on explicitly.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
# The second AI pass adds a Groq call per batch, which would change every
# existing test's call count. Rule checks stay on (they make no calls); the
# tests in test_answer_verification.py switch the AI pass on explicitly.
os.environ.setdefault("ENABLE_LLM_ANSWER_VERIFICATION", "false")

from app.db import Base, get_session  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services import blueprint_jobs  # noqa: E402
from app.services import generation as generation_service  # noqa: E402
from generation_engine.engine import GenerationEngine  # noqa: E402
from generation_engine.exceptions import GroqAPIError  # noqa: E402


# ---------------------------------------------------------------------------
# Fake generation
# ---------------------------------------------------------------------------


# Distinct question stems, cycled through so a batch never contains two
# texts similar enough to trip Module A's 0.90 near-duplicate threshold.
_STEMS = [
    "Explain how green plants capture sunlight during the day.",
    "Describe the role of stomata in gas exchange.",
    "Why does water rise through the stem of a tall tree?",
    "What happens to starch stored in a leaf overnight?",
    "Compare aerobic respiration with anaerobic respiration.",
    "State the function of chlorophyll in a plant cell.",
    "How do root hairs increase absorption from the soil?",
    "Outline the path of carbon dioxide from air into a leaf.",
    "Discuss why deforestation affects rainfall patterns.",
    "Identify the products formed when glucose is oxidised.",
    "Explain the difference between transpiration and evaporation.",
    "What role do veins play in transporting food around a plant?",
    "Describe an experiment that shows oxygen is released by pondweed.",
    "Why are desert plants able to survive with very little water?",
    "Summarise how minerals move from soil into plant tissue.",
    "Explain the importance of sunlight intensity for crop yield.",
    "How does a waxy cuticle help a leaf conserve moisture?",
    "State two ways farmers improve soil fertility naturally.",
    "Describe what happens inside a chloroplast during daylight.",
    "Why do leaves change colour when a plant is starved of nitrogen?",
    "Explain how insects assist in the pollination of flowers.",
    "What is the purpose of the xylem tissue in vascular plants?",
    "Discuss the effect of temperature on the rate of photosynthesis.",
    "How is energy stored by plants passed along a food chain?",
    "Describe the structure of a typical dicot leaf in cross section.",
    "Explain why crops are rotated between growing seasons.",
    "What evidence shows that plants respire as well as photosynthesise?",
    "Outline how carbon returns to the atmosphere after a plant dies.",
    "Describe the effect of waterlogging on root function.",
    "Why is magnesium considered an essential plant nutrient?",
]


class FakeGroqClient:
    """
    Stands in for GroqClient.complete_json.

    Produces `count` distinct, schema-valid questions shaped to whatever the
    prompt asked for. `raise_error` makes every call fail, to exercise the 502
    path; `bad_payload` returns unusable items, to exercise the 422 path.

    Question texts are drawn from `_STEMS` rather than templated off a random
    nonce, because Module A rejects near-duplicates at 0.90 similarity and a
    single template with a varying id is well above that threshold.
    """

    def __init__(
        self,
        *,
        raise_error: bool = False,
        bad_payload: bool = False,
        verifier: str = "agree",
    ):
        self.raise_error = raise_error
        self.bad_payload = bad_payload
        # How the answer-key verifier (second AI pass) behaves:
        #   "agree"     confirms every key
        #   "disagree"  contradicts every key
        #   "uncertain" is never confident
        #   "error"     the verification call itself fails
        #   "garbage"   returns unusable output
        #   "disagree_first"  contradicts only the first question of each call
        self.verifier = verifier
        self.calls: list[tuple[str, str]] = []
        self._served = 0

    @property
    def generation_calls(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if "answer-key verifier" not in c[0]]

    @property
    def verification_calls(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if "answer-key verifier" in c[0]]

    def _verify(self, user_prompt: str) -> list[dict]:
        """Answer a verifier prompt (see generation_engine/answer_verification.py)."""
        if self.verifier == "error":
            raise GroqAPIError("stubbed verifier failure")
        if self.verifier == "garbage":
            return [{"nonsense": True}, "bad"]
        items = json.loads(re.search(r"^\[.*\]$", user_prompt, re.M | re.S).group(0))
        results = []
        for n, item in enumerate(items):
            wrong = self.verifier == "disagree" or (self.verifier == "disagree_first" and n == 0)
            if "options" in item and "answer" not in item:  # MCQ: solved blind (no key shown)
                options = item["options"]
                # the stub always writes the correct option first ("The correct choice ...")
                right = next(k for k, v in options.items() if v.startswith("The correct choice"))
                choice = next(k for k in options if k != right) if wrong else right
                confidence = "low" if self.verifier == "uncertain" else "high"
                results.append(
                    {"index": item["index"], "choice": choice, "confidence": confidence,
                     "reasoning": "stub reasoning"}
                )
            else:  # descriptive: judged
                verdict = (
                    "uncertain" if self.verifier == "uncertain"
                    else "incorrect" if wrong else "correct"
                )
                results.append({"index": item["index"], "verdict": verdict, "reason": "stub reason"})
        return results

    async def complete_json(self, system_prompt: str, user_prompt: str) -> list[dict]:
        self.calls.append((system_prompt, user_prompt))
        if "answer-key verifier" in system_prompt:
            return self._verify(user_prompt)
        if self.raise_error:
            raise GroqAPIError("stubbed Groq failure")
        if self.bad_payload:
            return [{"text": "", "answer": ""}]

        count = _extract_count(user_prompt)
        q_type, marks = _extract_type_and_marks(user_prompt)
        # "Generate with figures": the prompt lists the figures as "F1 - ...",
        # "F2 - ...". Answer the way a model following those rules would: one
        # figure per question, spread round-robin, text pointing at the figure.
        refs = re.findall(r"^(F\d+) - ", user_prompt, re.M)
        items = []
        for _ in range(count):
            item = self._item(self._served, q_type, marks)
            if refs:
                item["figure_ref"] = refs[self._served % len(refs)]
                item["text"] = f"In the figure shown, {item['text'][0].lower()}{item['text'][1:]}"
            items.append(item)
            self._served += 1
        return items

    def _item(self, index: int, q_type: str, marks: int) -> dict:
        stem = _STEMS[index % len(_STEMS)]
        nonce = f"{index}-{uuid.uuid4().hex[:4]}"
        if q_type == "MCQ":
            return {
                "text": f"{stem} Choose the correct option.",
                "options": [
                    f"The correct choice for {nonce}",
                    f"An incorrect distractor about {nonce}",
                    f"A second distractor unrelated to {nonce}",
                    f"A third distractor covering something else entirely",
                ],
                "answer": f"The correct choice for {nonce}",
                "explanation": f"It is correct because of reason {nonce}.",
                "marks": 1,
                "topic": "stub-topic",
                "tags": ["stub"],
            }

        if q_type == "Fill":
            return {
                "text": f"{stem.rstrip('.?')}, which scientists call _____.",
                "answer": f"Newton {index}",
                "explanation": "",
                "topic": "stub-topic",
                "tags": ["stub"],
            }
        if q_type == "Match":
            # `marks` pairs, in correct order. Left items borrow distinct stems so
            # two questions never look alike to the near-duplicate check.
            return {
                "text": "Match the following terms with their descriptions:",
                "pairs": [
                    {
                        "left": _STEMS[(index * 5 + k) % len(_STEMS)].rstrip(".?"),
                        "right": f"Description {index}-{k} {uuid.uuid4().hex[:4]}",
                    }
                    for k in range(marks)
                ],
                "topic": "stub-topic",
                "tags": ["stub"],
            }

        answer = {
            1: f"Newton {nonce}",
            2: (
                f"The result is {nonce}. This follows because the underlying "
                f"principle applies directly to the given case."
            ),
            3: (
                f"1. The process begins with input {nonce} being absorbed.\n"
                f"2. The reaction converts it into a usable product.\n"
                f"3. The product supports growth throughout the organism."
            ),
            5: (
                f"1. Introduction: the process {nonce} is central to this "
                f"chapter and its causes are set out step by step below.\n"
                f"2. The initial step prepares the required inputs and sets up "
                f"the conditions needed for the reaction to proceed.\n"
                f"3. The main step transforms those inputs into the "
                f"intermediate products described in the textbook, so that "
                f"total input = total output at every stage.\n"
                f"4. Effects: the final product is distributed and used by the "
                f"wider system, which explains its practical importance.\n"
                f"5. Hence the overall result is that this process sustains "
                f"the system as a whole."
            ),
        }[marks]
        return {
            "text": stem,
            "answer": answer,
            # 1-mark answers must carry no explanation (forbid_explanation in
            # subject_formats.DEFAULT_MARKS_RULES).
            "explanation": "" if marks == 1 else f"Marking note for {nonce}.",
            "marks": marks,
            "topic": "stub-topic",
            "tags": ["stub"],
        }


def _extract_count(prompt: str) -> int:
    """Read the batch size back out of the prompt footer."""
    match = re.search(r"exactly\s+(\d+)\s+objects", prompt, re.I)
    return int(match.group(1)) if match else 1


def _extract_type_and_marks(prompt: str) -> tuple[str, int]:
    """
    Infer (type, marks) from the prompt text.

    The prompts in generation_engine/prompts.py never name the type or mark
    value as a bare token, so this matches a phrase unique to each template.
    The phrases are deliberately taken from the template bodies, not the
    per-subject notes — Math's note mentions "5-mark answers", which would
    otherwise misclassify every Math request as a Long one.
    """
    if "multiple-choice questions for" in prompt:
        return "MCQ", 1
    if "fill-in-the-blank questions for" in prompt:
        return "Fill", 1
    if "match-the-following questions for" in prompt:
        return "Match", int(re.search(r"exactly (\d+) pairs", prompt).group(1))
    if "one-mark questions for" in prompt:
        return "Short", 1
    if "Each answer must be 1-2 lines long" in prompt:
        return "Short", 2
    if "EXACTLY 3 distinct points" in prompt:
        return "Short", 3
    if "at least 4 distinct points or steps" in prompt:
        return "Long", 5
    raise AssertionError(f"FakeGroqClient could not classify prompt: {prompt[:200]}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
def groq_stub() -> FakeGroqClient:
    return FakeGroqClient()


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    """Rate limiting is off for the suite (see RATE_LIMIT_ENABLED above);
    tests that exercise it turn it on, and start from empty counters."""
    from app.ratelimit import limiter

    limiter.reset()
    yield
    limiter.reset()


async def sign_up(ac: AsyncClient, *, name: str = "Alice Teacher", email: str = "alice@school.test") -> dict:
    """Create an account and make `ac` send its token from now on."""
    response = await ac.post(
        "/auth/signup", json={"name": name, "email": email, "password": "Passw0rd-test"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    ac.headers["Authorization"] = f"Bearer {body['access_token']}"
    return body["user"]


@contextlib.asynccontextmanager
async def _app_client(session_factory, engine, *, signed_in: bool = True):
    """The app under test, wired to the in-memory DB and a stubbed Groq engine."""
    generation_service.set_engine(engine)
    blueprint_jobs.set_session_factory(session_factory)
    blueprint_jobs.reset()

    async def _override():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        if signed_in:
            await sign_up(ac)
        yield ac
    fastapi_app.dependency_overrides.clear()
    generation_service.set_engine(None)
    blueprint_jobs.set_session_factory(None)
    blueprint_jobs.reset()


@pytest_asyncio.fixture
async def client(session_factory, groq_stub):
    """A client signed in as alice@school.test (the default test user)."""
    async with _app_client(session_factory, GenerationEngine(groq_client=groq_stub)) as ac:
        yield ac


@pytest_asyncio.fixture
async def anon_client(session_factory, groq_stub):
    """A client with no credentials."""
    async with _app_client(
        session_factory, GenerationEngine(groq_client=groq_stub), signed_in=False
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def bob_client(client):
    """A second signed-in user talking to the same app and database as `client`."""
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as bob:
        await sign_up(bob, name="Bob Teacher", email="bob@school.test")
        yield bob


@pytest_asyncio.fixture
async def admin_client(client, session_factory):
    """An administrator (the only role that can change the figure library).

    Admin can't be chosen at sign-up, so the account is created normally and
    then promoted directly in the database, the way scripts/make_admin.py does.
    """
    from sqlalchemy import update

    from app.models import User

    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as admin:
        user = await sign_up(admin, name="Ada Admin", email="ada@school.test")
        async with session_factory() as session:
            await session.execute(update(User).where(User.email == "ada@school.test").values(role="Admin"))
            await session.commit()
        assert (await admin.get("/auth/me")).json()["role"] == "Admin"
        yield admin


@pytest_asyncio.fixture
async def failing_client(session_factory):
    """Client whose Groq calls always fail — for the 502 path."""
    engine = GenerationEngine(groq_client=FakeGroqClient(raise_error=True))
    async with _app_client(session_factory, engine) as ac:
        yield ac


@pytest_asyncio.fixture
async def bad_payload_client(session_factory):
    """Client whose Groq calls return unusable output — for the 422 path."""
    engine = GenerationEngine(groq_client=FakeGroqClient(bad_payload=True))
    async with _app_client(session_factory, engine) as ac:
        yield ac


# --- helpers ---------------------------------------------------------------


async def generate_questions(client, **overrides) -> list[dict]:
    """POST /generate with sensible defaults; returns the question list."""
    body = {
        "subject": "Science",
        "chapter": "Photosynthesis",
        "type": "Short",
        "grade": 8,
        "marks": 3,
        "difficulty": "medium",
        "count": 3,
    }
    body.update(overrides)
    response = await client.post("/generate", json=body)
    assert response.status_code == 200, response.text
    return response.json()["questions"]


@pytest.fixture
def practice_shortfall_on(monkeypatch):
    """Practice sessions fill a thin chapter by generating on demand (off by default)."""
    from app.config import settings

    monkeypatch.setattr(settings, "practice_generate_shortfall", True)
