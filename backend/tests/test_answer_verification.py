"""Answer-key verification: the AI pass, the decision logic, the engine's
on-demand `verify_answers`, the `POST /questions/verify` endpoint, and what
reaches the database. Generation itself no longer verifies anything."""
from __future__ import annotations

import dataclasses
import json
import uuid

import pytest
from sqlalchemy import update

from app.models import Question as QuestionRow
from app.schemas.common import QuestionOut
from app.services import questions as question_service
from app.services.syllabus import resolve_chapter
from generation_engine import engine as engine_module
from generation_engine.answer_verification import (
    REJECTED,
    UNVERIFIED,
    VERIFIED,
    LlmVerdict,
    build_judge_prompt,
    build_mcq_prompt,
    decide,
    llm_verdicts,
    verify_questions,
)
from generation_engine.engine import GenerationEngine
from generation_engine.exceptions import GroqAPIError
from generation_engine.rule_checks import NOT_APPLICABLE, RuleResult
from generation_engine.schemas import (
    Difficulty,
    GenerationRequest,
    Question,
    QuestionType,
    Subject,
)

from .conftest import FakeGroqClient
from .test_service_edge_cases import _engine_question


# --- helpers ---------------------------------------------------------------------


@pytest.fixture
def ai_pass(monkeypatch):
    """Switch the second AI pass on (the suite turns it off by default)."""

    def enable(**overrides):
        monkeypatch.setattr(
            engine_module,
            "settings",
            dataclasses.replace(
                engine_module.settings, enable_llm_answer_verification=True, **overrides
            ),
        )

    enable()
    return enable


def engine_settings(monkeypatch, **overrides):
    monkeypatch.setattr(
        engine_module, "settings", dataclasses.replace(engine_module.settings, **overrides)
    )


def science_request(count=3, q_type=QuestionType.MCQ, marks=1):
    return GenerationRequest(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=q_type,
        grade=8, marks=marks, difficulty=Difficulty.EASY, count=count,
    )


def math_request(count=2):
    return GenerationRequest(
        subject=Subject.MATH, chapter="Arithmetic", type=QuestionType.SHORT,
        grade=8, marks=1, difficulty=Difficulty.EASY, count=count,
    )


def short1(text, answer):
    return {"text": text, "answer": answer, "explanation": "", "topic": "t", "tags": []}


class ScriptedGroq:
    """Returns a prepared batch for each generation call; the verifier says 'correct'."""

    def __init__(self, *batches):
        self.batches = list(batches)
        self.calls: list[tuple[str, str]] = []

    @property
    def generation_calls(self):
        return [c for c in self.calls if "answer-key verifier" not in c[0]]

    @property
    def verification_calls(self):
        return [c for c in self.calls if "answer-key verifier" in c[0]]

    async def complete_json(self, system, user):
        self.calls.append((system, user))
        if "answer-key verifier" in system:
            items = json.loads(user[user.index("[{"): user.rindex("}]") + 2])
            return [{"index": i["index"], "verdict": "correct", "reason": "ok"} for i in items]
        return self.batches.pop(0)


def mcq(text="Which gas do plants absorb?", answer="Carbon dioxide"):
    return Question(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=QuestionType.MCQ, grade=8,
        text=text, options=[answer, "Neon", "Argon", "Helium"], answer=answer,
        explanation="Plants use it for photosynthesis.", marks=1, difficulty=Difficulty.EASY,
    )


def descriptive(text="State the function of chlorophyll.", answer="It absorbs sunlight."):
    return Question(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=QuestionType.SHORT, grade=8,
        text=text, answer=answer, explanation="", marks=1, difficulty=Difficulty.EASY,
    )


# --- decision logic -----------------------------------------------------------------

OK = RuleResult("ok", "Checked by calculation: 2 + 2 = 4.")
BAD = RuleResult("mismatch", "Calculation gives 4 but the key says 5.")
AGREE = LlmVerdict("agree", "Independently solved by a second AI pass.")
DISAGREE = LlmVerdict("disagree", "A second AI pass chose X.")
UNSURE = LlmVerdict("uncertain", "Not confident.")


@pytest.mark.parametrize(
    "rule,verdict,attempted,status",
    [
        (OK, None, False, VERIFIED),
        (OK, DISAGREE, True, VERIFIED),  # a rule is proof; it outranks the AI pass
        (BAD, AGREE, True, REJECTED),  # ...in both directions
        (BAD, None, False, REJECTED),
        (NOT_APPLICABLE, AGREE, True, VERIFIED),
        (NOT_APPLICABLE, DISAGREE, True, REJECTED),
        (NOT_APPLICABLE, UNSURE, True, UNVERIFIED),
        (NOT_APPLICABLE, None, True, UNVERIFIED),
        (NOT_APPLICABLE, None, False, UNVERIFIED),
    ],
)
def test_decide(rule, verdict, attempted, status):
    result = decide(rule, verdict, llm_attempted=attempted)
    assert result.status == status
    assert result.note


def test_decide_notes_distinguish_failed_from_not_applicable():
    failed = decide(NOT_APPLICABLE, None, llm_attempted=True)
    skipped = decide(NOT_APPLICABLE, None, llm_attempted=False)
    assert "could not be completed" in failed.note
    assert "No automatic check" in skipped.note


# --- the AI pass: prompts ------------------------------------------------------------


def test_mcq_prompt_never_shows_the_answer_key():
    q = mcq()
    system, user = build_mcq_prompt([q])
    assert "Carbon dioxide" in user  # it's one of the options, as it must be
    assert '"answer"' not in user
    assert q.explanation not in user
    assert "correct answer" not in user.lower()
    assert "answer-key verifier" in system


def test_judge_prompt_shows_the_answer_and_asks_for_scepticism():
    q = descriptive()
    _, user = build_judge_prompt([q])
    assert q.answer in user
    assert "re-derive" in user


# --- the AI pass: parsing -------------------------------------------------------------


class Canned:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, 0

    async def complete_json(self, system, user):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


async def test_mcq_agree_and_disagree_by_letter():
    q = mcq()  # key is option A
    out = await llm_verdicts(
        Canned([{"index": 0, "choice": "A", "confidence": "high", "reasoning": "r"}]), [q]
    )
    assert out[0].outcome == "agree"
    out = await llm_verdicts(
        Canned([{"index": 0, "choice": "b", "confidence": "medium", "reasoning": "Neon is wrong"}]),
        [q],
    )
    assert out[0].outcome == "disagree"
    assert "Neon" in out[0].detail and "Carbon dioxide" in out[0].detail


@pytest.mark.parametrize(
    "entry",
    [
        {"index": 0, "choice": "A", "confidence": "low"},  # not confident
        {"index": 0, "choice": "Z", "confidence": "high"},  # not an option
        {"index": 0, "confidence": "high"},  # no choice
        {"index": 0, "choice": "", "confidence": "high"},
    ],
)
async def test_mcq_unusable_or_unconfident_is_uncertain(entry):
    out = await llm_verdicts(Canned([entry]), [mcq()])
    assert out[0].outcome == "uncertain"


async def test_descriptive_verdicts():
    q = descriptive()
    for verdict, outcome in (("correct", "agree"), ("incorrect", "disagree"), ("uncertain", "uncertain"), ("maybe", "uncertain")):
        out = await llm_verdicts(Canned([{"index": 0, "verdict": verdict, "reason": "r"}]), [q])
        assert out[0].outcome == outcome, verdict


@pytest.mark.parametrize(
    "reply",
    [
        [],
        [{"index": 5, "verdict": "correct"}],  # index out of range
        [{"index": True, "verdict": "correct"}],  # bool is not an index
        [{"index": "0", "verdict": "correct"}],
        ["junk", None, 3],
        [{"verdict": "correct"}],  # no index
        {"not": "a list"},
    ],
)
async def test_malformed_replies_leave_questions_unverified(reply):
    out = await llm_verdicts(Canned(reply), [descriptive()])
    assert out == [None]


async def test_a_failed_call_leaves_the_chunk_unverified_instead_of_raising():
    out = await llm_verdicts(Canned(error=GroqAPIError("boom")), [descriptive(), descriptive("Other?")])
    assert out == [None, None]


async def test_questions_are_verified_in_chunks():
    qs = [descriptive(f"Question number {i} about plants?") for i in range(7)]
    client = Canned([])
    await llm_verdicts(client, qs, chunk_size=3)
    assert client.calls == 3  # 3 + 3 + 1


async def test_indexes_are_local_to_each_chunk():
    qs = [descriptive(f"Question number {i} about plants?") for i in range(4)]

    class Echo:
        async def complete_json(self, system, user):
            items = json.loads(user[user.index("[{"): user.rindex("}]") + 2])
            return [{"index": i["index"], "verdict": "incorrect", "reason": "x"} for i in items]

    out = await llm_verdicts(Echo(), qs, chunk_size=2)
    assert [v.outcome for v in out] == ["disagree"] * 4


async def test_verify_questions_never_spends_the_ai_pass_on_rule_decided_questions():
    right = Question(
        subject=Subject.MATH, chapter="c", type=QuestionType.SHORT, grade=8,
        text="What is 12 × 15?", answer="180", marks=1, difficulty=Difficulty.EASY,
    )
    wrong = right.model_copy(update={"text": "What is 9 × 9?", "answer": "80"})
    open_q = descriptive("Why is zero neither positive nor negative?", "It is the origin.")
    open_q = open_q.model_copy(update={"subject": Subject.MATH})
    client = ScriptedGroq()
    results = await verify_questions([right, wrong, open_q], client=client, chunk_size=10)

    assert [r.status for r in results] == [VERIFIED, REJECTED, VERIFIED]
    assert len(client.verification_calls) == 1
    assert "Why is zero" in client.verification_calls[0][1]
    assert "12 × 15" not in client.verification_calls[0][1]


async def test_verify_questions_with_everything_off():
    results = await verify_questions([descriptive()], client=None, use_rules=False, use_llm=False)
    assert [r.status for r in results] == [UNVERIFIED]
    assert await verify_questions([], client=None) == []


# --- generation no longer verifies ---------------------------------------------------------------


async def test_generation_does_not_verify_answers(ai_pass):
    groq = FakeGroqClient(verifier="agree")
    questions, report = await GenerationEngine(groq_client=groq).generate(science_request(3))

    assert [q.verification_status for q in questions] == [None] * 3
    assert len(groq.generation_calls) == 1 and len(groq.verification_calls) == 0
    assert not {"answers_verified", "answers_unverified", "dropped_wrong_answer", "flagged_kept"} & set(
        report.as_dict()
    )


async def test_generation_keeps_a_wrong_key_for_the_teacher_to_verify_later(monkeypatch):
    """A wrong key is no longer regenerated at generation time: it is found by 'Verify answers'."""
    engine_settings(monkeypatch, enable_llm_answer_verification=False)
    groq = ScriptedGroq([short1("What is 12 × 15?", "170"), short1("Calculate 144 ÷ 12", "13")])
    questions, report = await GenerationEngine(groq_client=groq).generate(math_request(2))

    assert [q.answer for q in questions] == ["170", "13"]
    assert [q.verification_status for q in questions] == [None, None]
    assert report.attempts == 1 and len(groq.generation_calls) == 1


# --- the engine: verify_answers (rule checks) ----------------------------------------------------


def math_short(text, answer):
    return Question(
        subject=Subject.MATH, chapter="Arithmetic", type=QuestionType.SHORT, grade=8,
        text=text, answer=answer, explanation="", marks=1, difficulty=Difficulty.EASY,
    )


async def test_a_wrong_key_found_by_a_rule_is_flagged(monkeypatch):
    engine_settings(monkeypatch, enable_llm_answer_verification=False)
    asked = [math_short("What is 12 × 15?", "170"), math_short("Calculate 144 ÷ 12", "12")]
    out = await GenerationEngine(groq_client=ScriptedGroq()).verify_answers(asked)

    assert [q.verification_status for q in out] == ["flagged", "verified"]
    assert "170" in out[0].verification_note
    assert "Checked by calculation" in out[1].verification_note
    # the inputs are left alone; the results are copies
    assert [q.verification_status for q in asked] == [None, None]


async def test_verify_answers_never_regenerates_anything(monkeypatch):
    engine_settings(monkeypatch, enable_llm_answer_verification=False)
    groq = ScriptedGroq()
    out = await GenerationEngine(groq_client=groq).verify_answers([math_short("What is 12 × 15?", "170")])
    assert [q.verification_status for q in out] == ["flagged"]
    assert groq.calls == []  # no generation call, and no AI pass (switched off)


async def test_verify_answers_with_nothing_to_check():
    assert await GenerationEngine(groq_client=ScriptedGroq()).verify_answers([]) == []


async def test_with_both_checks_off_every_question_reads_unverified(monkeypatch):
    engine_settings(
        monkeypatch, enable_llm_answer_verification=False, enable_answer_rule_checks=False
    )
    out = await GenerationEngine(groq_client=FakeGroqClient()).verify_answers(
        [math_short("What is 12 × 15?", "170")]
    )
    assert [q.verification_status for q in out] == ["unverified"]


# --- the engine: verify_answers (the AI pass) ----------------------------------------------------


async def _generated(groq, request):
    engine = GenerationEngine(groq_client=groq)
    questions, _ = await engine.generate(request)
    return engine, questions


async def test_ai_pass_confirms_mcq_keys(ai_pass):
    groq = FakeGroqClient(verifier="agree")
    engine, questions = await _generated(groq, science_request(3))
    out = await engine.verify_answers(questions)

    assert [q.verification_status for q in out] == ["verified"] * 3
    assert all("second AI pass" in q.verification_note for q in out)
    assert len(groq.generation_calls) == 1 and len(groq.verification_calls) == 1  # one call per batch


async def test_mcq_verifier_is_never_shown_the_key_in_a_real_run(ai_pass):
    groq = FakeGroqClient()
    engine, questions = await _generated(groq, science_request(2))
    await engine.verify_answers(questions)
    prompt = groq.verification_calls[0][1]
    assert '"answer"' not in prompt
    assert all(q.explanation not in prompt for q in questions)


async def test_ai_pass_for_descriptive_answers(ai_pass):
    groq = FakeGroqClient(verifier="agree")
    engine, questions = await _generated(groq, science_request(2, QuestionType.SHORT, 2))
    out = await engine.verify_answers(questions)
    assert [q.verification_status for q in out] == ["verified"] * 2


async def test_ai_disagreement_flags_the_question_without_regenerating(ai_pass):
    groq = FakeGroqClient(verifier="disagree")
    engine, questions = await _generated(groq, science_request(3))
    out = await engine.verify_answers(questions)

    assert [q.verification_status for q in out] == ["flagged"] * 3
    assert all("second AI pass chose" in q.verification_note for q in out)
    assert len(groq.generation_calls) == 1  # nothing was generated to replace them


async def test_a_partly_wrong_batch_keeps_the_verified_ones(ai_pass):
    groq = FakeGroqClient(verifier="disagree_first")
    engine, questions = await _generated(groq, science_request(3))
    out = await engine.verify_answers(questions)
    assert sorted(q.verification_status for q in out) == ["flagged", "verified", "verified"]


async def test_unconfident_verifier_leaves_questions_unverified(ai_pass):
    groq = FakeGroqClient(verifier="uncertain")
    engine, questions = await _generated(groq, science_request(3))
    out = await engine.verify_answers(questions)
    assert [q.verification_status for q in out] == ["unverified"] * 3


@pytest.mark.parametrize("mode", ["error", "garbage"])
async def test_a_failing_verifier_never_fails_verification(ai_pass, mode):
    groq = FakeGroqClient(verifier=mode)
    engine, questions = await _generated(groq, science_request(3))
    out = await engine.verify_answers(questions)
    assert [q.verification_status for q in out] == ["unverified"] * 3
    assert all("could not be completed" in q.verification_note for q in out)


async def test_verification_runs_in_chunks(ai_pass):
    ai_pass(verification_chunk_size=3)
    groq = FakeGroqClient()
    engine, questions = await _generated(groq, science_request(7))
    await engine.verify_answers(questions)
    assert len(groq.verification_calls) == 3


async def test_a_separate_verifier_client_is_used_for_the_second_pass(ai_pass):
    generator, verifier = FakeGroqClient(), FakeGroqClient()
    engine = GenerationEngine(groq_client=generator, verifier_client=verifier)
    questions, _ = await engine.generate(science_request(2))
    out = await engine.verify_answers(questions)
    assert len(generator.verification_calls) == 0 and len(verifier.verification_calls) == 1
    assert all(q.verification_status == "verified" for q in out)


# --- through the API ---------------------------------------------------------------------------

BASE = {
    "subject": "Science", "chapter": "Photosynthesis", "type": "MCQ",
    "grade": 8, "marks": 1, "difficulty": "easy", "count": 3,
}


async def _verify(client, questions):
    return await client.post(
        "/questions/verify", json={"question_ids": [q["id"] for q in questions]}
    )


async def test_api_generation_returns_unverified_questions_and_makes_no_verification_call(
    client, groq_stub, ai_pass
):
    body = (await client.post("/generate", json=BASE)).json()

    assert {q["verification_status"] for q in body["questions"]} == {"unverified"}
    assert groq_stub.verification_calls == []
    assert "answers_verified" not in body["report"]


async def test_verify_endpoint_checks_stores_and_returns_the_result(client, ai_pass):
    questions = (await client.post("/generate", json=BASE)).json()["questions"]
    response = await _verify(client, questions)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [q["id"] for q in body["questions"]] == [q["id"] for q in questions]  # same order
    assert [q["verification_status"] for q in body["questions"]] == ["verified"] * 3
    assert all(q["verification_note"] for q in body["questions"])
    assert (body["verified"], body["unverified"], body["flagged"]) == (3, 0, 0)

    listed = (await client.get("/questions", params={"subject": "Science"})).json()
    assert {q["verification_status"] for q in listed["results"]} == {"verified"}


async def test_verify_endpoint_flags_a_wrong_key(client, groq_stub, ai_pass):
    questions = (await client.post("/generate", json=BASE)).json()["questions"]
    groq_stub.verifier = "disagree"
    body = (await _verify(client, questions)).json()

    assert {q["verification_status"] for q in body["questions"]} == {"flagged"}
    assert (body["verified"], body["unverified"], body["flagged"]) == (0, 0, 3)
    assert all("second AI pass chose" in q["verification_note"] for q in body["questions"])


async def test_verify_endpoint_survives_a_failing_ai_pass(client, groq_stub, ai_pass):
    questions = (await client.post("/generate", json=BASE)).json()["questions"]
    groq_stub.verifier = "error"
    response = await _verify(client, questions)
    assert response.status_code == 200
    assert response.json()["unverified"] == 3


async def test_verify_endpoint_with_rule_checks_only(client, groq_stub, monkeypatch):
    """Maths keys are checked by calculation, with no AI pass and no stub that knows the answer."""
    engine_settings(monkeypatch, enable_llm_answer_verification=False)
    from app.services import generation as generation_service

    groq = ScriptedGroq([short1("What is 12 × 15?", "170"), short1("What is 25% of 240?", "60")])
    generation_service.set_engine(GenerationEngine(groq_client=groq))
    made = await client.post(
        "/generate",
        json={"subject": "Math", "chapter": "Arithmetic", "type": "Short", "grade": 8,
              "marks": 1, "difficulty": "easy", "count": 2},
    )
    assert made.status_code == 200, made.text
    assert {q["verification_status"] for q in made.json()["questions"]} == {"unverified"}

    body = (await _verify(client, made.json()["questions"])).json()
    by_text = {q["text"]: q for q in body["questions"]}
    assert by_text["What is 12 × 15?"]["verification_status"] == "flagged"
    assert by_text["What is 25% of 240?"]["verification_status"] == "verified"
    assert groq.verification_calls == []


async def test_verify_endpoint_unknown_question_is_404(client):
    response = await client.post("/questions/verify", json={"question_ids": [str(uuid.uuid4())]})
    assert response.status_code == 404


@pytest.mark.parametrize("ids", [[], ["not-a-uuid"]])
async def test_verify_endpoint_rejects_a_bad_body(client, ids):
    response = await client.post("/questions/verify", json={"question_ids": ids})
    assert response.status_code in (400, 422)


async def test_verify_endpoint_caps_the_batch_size(client):
    ids = [str(uuid.uuid4()) for _ in range(51)]
    response = await client.post("/questions/verify", json={"question_ids": ids})
    assert response.status_code in (400, 422)


async def test_verify_endpoint_requires_sign_in(anon_client):
    response = await anon_client.post("/questions/verify", json={"question_ids": [str(uuid.uuid4())]})
    assert response.status_code == 401


async def test_verify_endpoint_ignores_repeated_ids(client, ai_pass):
    [q] = (await client.post("/generate", json={**BASE, "count": 1})).json()["questions"]
    body = (await _verify(client, [q, q])).json()
    assert [x["id"] for x in body["questions"]] == [q["id"]]


async def test_anyone_signed_in_can_verify_a_question_someone_else_generated(client, bob_client, ai_pass):
    questions = (await client.post("/generate", json=BASE)).json()["questions"]
    response = await _verify(bob_client, questions)
    assert response.status_code == 200
    assert response.json()["verified"] == 3


async def test_a_stored_question_in_an_unexpected_shape_reads_unverified_not_500(
    client, db_session, ai_pass
):
    [q] = (await client.post("/generate", json={**BASE, "count": 1})).json()["questions"]
    await db_session.execute(update(QuestionRow).values(options=["only one option"]))
    await db_session.commit()

    response = await _verify(client, [q])
    assert response.status_code == 200
    [got] = response.json()["questions"]
    assert got["verification_status"] == "unverified"
    assert got["verification_note"].startswith("Could not be checked")


async def test_flagged_questions_are_not_served_from_the_cache(client, groq_stub, ai_pass):
    first = (await client.post("/generate", json=BASE)).json()
    groq_stub.verifier = "disagree"
    await _verify(client, first["questions"])
    flagged_ids = {q["id"] for q in first["questions"]}
    calls_before = len(groq_stub.generation_calls)

    second = (await client.post("/generate", json=BASE)).json()

    assert second["cached"] == 0  # the flagged ones were not reused
    assert len(groq_stub.generation_calls) > calls_before
    assert not flagged_ids & {q["id"] for q in second["questions"]}


async def test_verified_questions_are_cached_as_before(client, ai_pass):
    first = (await client.post("/generate", json=BASE)).json()
    await _verify(client, first["questions"])
    second = (await client.post("/generate", json=BASE)).json()
    assert second["cached"] == 3 and second["generated"] == 0
    # same questions (cache order among rows created in the same instant isn't defined)
    assert {q["id"] for q in second["questions"]} == {q["id"] for q in first["questions"]}
    assert {q["verification_status"] for q in second["questions"]} == {"verified"}


async def test_practice_never_serves_flagged_questions(client, groq_stub, ai_pass, monkeypatch):
    from app.services import practice as practice_service

    monkeypatch.setattr(practice_service.settings, "practice_generate_shortfall", False)
    questions = (await client.post("/generate", json={**BASE, "count": 2})).json()["questions"]
    body = {"subject": "Science", "chapter": "Photosynthesis", "type": "MCQ", "grade": 8, "count": 2}

    groq_stub.verifier = "disagree"
    await _verify(client, questions)
    response = await client.post("/practice/sessions", json=body)
    assert response.status_code == 422  # nothing trustworthy to practise on

    groq_stub.verifier = "agree"
    await _verify(client, questions)  # re-verifying overwrites the earlier result
    assert (await client.post("/practice/sessions", json=body)).status_code == 201


async def test_a_teacher_can_still_put_a_flagged_question_in_a_paper(client, groq_stub, ai_pass):
    questions = (await client.post("/generate", json={**BASE, "count": 1})).json()["questions"]
    groq_stub.verifier = "disagree"
    await _verify(client, questions)
    r = await client.post(
        "/papers",
        json={"title": "P", "subject": "Science", "question_ids": [questions[0]["id"]]},
    )
    assert r.status_code == 201
    assert r.json()["questions"][0]["question"]["verification_status"] == "flagged"


async def test_questions_from_before_verification_read_as_unverified(client, db_session):
    [q] = (await client.post("/generate", json={**BASE, "count": 1})).json()["questions"]
    await db_session.execute(
        update(QuestionRow).values(verification_status=None, verification_note=None)
    )
    await db_session.commit()
    got = (await client.get(f"/questions/{q['id']}")).json()
    assert got["verification_status"] == "unverified" and got["verification_note"] is None


# --- persistence details ---------------------------------------------------------------------------


async def test_persist_batch_stores_the_verification_fields(db_session):
    chapter = await resolve_chapter(db_session, Subject.SCIENCE, "Photosynthesis")
    [row] = await question_service.persist_batch(
        db_session,
        [_engine_question("What does a stoma do?", verification_status="verified", verification_note="n")],
        chapter=chapter,
    )
    assert (row.verification_status, row.verification_note) == ("verified", "n")


async def test_a_later_verified_copy_upgrades_an_unverified_twin(db_session):
    chapter = await resolve_chapter(db_session, Subject.SCIENCE, "Photosynthesis")
    text = "Name the pigment that makes leaves green."
    [first] = await question_service.persist_batch(
        db_session, [_engine_question(text, verification_status="unverified")], chapter=chapter
    )
    [again] = await question_service.persist_batch(
        db_session,
        [_engine_question(text, verification_status="verified", verification_note="checked")],
        chapter=chapter,
    )
    assert again.id == first.id
    assert (again.verification_status, again.verification_note) == ("verified", "checked")


async def test_a_different_key_does_not_upgrade_the_stored_status(db_session):
    chapter = await resolve_chapter(db_session, Subject.SCIENCE, "Photosynthesis")
    text = "Name the gas released in photosynthesis."
    [first] = await question_service.persist_batch(
        db_session, [_engine_question(text, answer="Oxygen", verification_status="flagged")], chapter=chapter
    )
    [again] = await question_service.persist_batch(
        db_session,
        [_engine_question(text, answer="Methane", verification_status="verified")],
        chapter=chapter,
    )
    assert again.id == first.id and again.verification_status == "flagged"


def test_question_out_defaults_to_unverified():
    assert QuestionOut.model_fields["verification_status"].default == "unverified"
