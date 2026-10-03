"""
Figure-based generation (the "figure library with metadata" option).

The model never sees an image. It is given each figure's caption, topic and
labelled parts as text, names the figure a question is about by a short
reference (F1, F2 ...), and the engine attaches the real `figure_id`. These
tests cover the prompt, the reference mapping, the checks against the metadata,
and the answer-key verifier receiving the same description.
"""
import dataclasses
import json

import pytest

from generation_engine import engine as engine_module
from generation_engine.engine import GenerationEngine
from generation_engine.exceptions import GenerationValidationError
from generation_engine.prompts import build_prompt
from generation_engine.schemas import (
    Difficulty,
    FigureContext,
    GenerationRequest,
    Question,
    QuestionType,
    Subject,
)
from generation_engine.answer_verification import build_judge_prompt, build_mcq_prompt
from generation_engine.validation import (
    build_question,
    check_figure_question,
    find_duplicates,
    label_keys,
)

CELL = FigureContext(
    id="11111111-1111-1111-1111-111111111111",
    caption="Plant cell",
    topic="Cell structure",
    labels=["A: nucleus", "B: cell wall", "C: chloroplast"],
)
WATER = FigureContext(
    id="22222222-2222-2222-2222-222222222222",
    caption="The water cycle",
    labels=["1: evaporation", "2: condensation", "3: precipitation"],
)


def make_request(**overrides) -> GenerationRequest:
    base = dict(
        subject=Subject.SCIENCE,
        chapter="Cell Structure",
        type=QuestionType.SHORT,
        grade=8,
        marks=2,
        difficulty=Difficulty.MEDIUM,
        count=2,
        figures=[CELL, WATER],
    )
    base.update(overrides)
    return GenerationRequest(**base)


def raw_item(**overrides) -> dict:
    item = {
        "text": "In the figure shown, what is the function of the part labelled A?",
        "answer": "It controls the activities of the cell. It holds the genetic material.",
        "explanation": "",
        "topic": "Cell structure",
        "tags": ["cell"],
        "figure_ref": "F1",
    }
    item.update(overrides)
    return item


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    # The engine holds its own reference to the settings object, so patch that
    # one: no second AI pass (these tests script every Groq call), one retry.
    monkeypatch.setattr(
        engine_module,
        "settings",
        dataclasses.replace(
            engine_module.settings,
            enable_llm_answer_verification=False,
            max_regeneration_retries=1,
        ),
    )


# --- prompt --------------------------------------------------------------


def test_prompt_lists_each_figure_with_its_metadata_and_a_short_reference():
    _, user = build_prompt(make_request())
    assert "F1 - Caption: Plant cell. Topic: Cell structure. Labelled parts: A: nucleus; B: cell wall; C: chloroplast" in user
    assert "F2 - Caption: The water cycle" in user
    assert '"figure_ref"' in user
    # the real ids are never shown to the model
    assert CELL.id not in user and WATER.id not in user


def test_prompt_tells_the_model_not_to_invent_or_leak():
    _, user = build_prompt(make_request())
    assert "cannot see the images" in user
    assert "Do NOT invent" in user
    assert "never contain its own answer" in user


def test_prompt_without_figures_is_unchanged():
    plain = make_request(figures=None)
    _, user = build_prompt(plain)
    assert "figure_ref" not in user and "Figures." not in user


def test_figure_prompt_still_matches_the_marks_template():
    # The stubbed Groq clients classify prompts by phrases in the template body.
    _, user = build_prompt(make_request(type=QuestionType.SHORT, marks=3))
    assert "EXACTLY 3 distinct points" in user


# --- reference -> figure_id ----------------------------------------------


def test_build_question_attaches_the_figure_from_its_reference():
    result = build_question(raw_item(figure_ref="f2"), make_request())
    assert result.error is None
    q = result.question
    assert q.figure_id == WATER.id
    assert "The water cycle" in q.figure_context


def test_build_question_rejects_a_missing_or_unknown_reference():
    for bad in (None, "", "F9", CELL.id):
        result = build_question(raw_item(figure_ref=bad), make_request())
        assert result.question is None
        assert "figure_ref must be one of F1, F2" in result.error


def test_figure_ref_is_ignored_when_the_request_has_no_figures():
    result = build_question(raw_item(figure_ref="F1"), make_request(figures=None))
    assert result.error is None
    assert result.question.figure_id is None


def test_figure_context_is_never_serialised():
    q = build_question(raw_item(), make_request()).question
    assert "figure_context" not in q.model_dump()
    assert q.model_dump()["figure_id"] == CELL.id


# --- checks against the metadata ----------------------------------------


def test_label_keys_parses_letters_and_numbers():
    assert label_keys(["A: nucleus", "3 - evaporation", "b) root", "plain"]) == {
        "A": "nucleus",
        "3": "evaporation",
        "B": "root",
    }


def _q(request, **kw):
    return build_question(raw_item(**kw), request).question


def test_a_label_that_is_not_in_the_figure_is_rejected():
    req = make_request()
    problems = check_figure_question(_q(req, text="Name the part labelled D in the figure."), req)
    assert any('"D"' in p and "do not invent labels" in p for p in problems)


def test_a_real_label_passes():
    req = make_request()
    assert check_figure_question(_q(req), req) == []


def test_a_question_that_never_mentions_the_figure_is_rejected():
    req = make_request()
    problems = check_figure_question(_q(req, text="What does the nucleus do?"), req)
    assert any("never refers to the figure" in p for p in problems)


def test_a_question_that_states_its_own_answer_is_rejected():
    req = make_request(type=QuestionType.SHORT, marks=1)
    q = _q(
        req,
        text="Identify the nucleus labelled A in the figure.",
        answer="Nucleus",
        explanation="",
    )
    assert any("contains its own answer" in p for p in check_figure_question(q, req))


def test_label_keys_are_only_checked_when_the_figure_has_keyed_labels():
    plain = FigureContext(id="33333333-3333-3333-3333-333333333333", caption="Leaf", labels=["stomata"])
    req = make_request(figures=[plain])
    q = build_question(raw_item(text="In the figure shown, what is the part labelled Z?"), req).question
    assert check_figure_question(q, req) == []


def test_non_figure_questions_always_pass():
    req = make_request(figures=None)
    q = build_question(raw_item(text="What does the nucleus do?"), req).question
    assert check_figure_question(q, req) == []


# --- duplicates ----------------------------------------------------------


def test_same_wording_about_different_figures_is_not_a_duplicate():
    req = make_request()
    a = _q(req, text="In the figure shown, name the part labelled A.", figure_ref="F1")
    b = _q(req, text="In the figure shown, name the part labelled A.", figure_ref="F2")
    c = _q(req, text="In the figure shown, name the part labelled A.", figure_ref="F1")
    assert find_duplicates([a, b]) == set()
    assert find_duplicates([a, b, c]) == {2}


# --- the engine end to end ----------------------------------------------


class ScriptedGroq:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    async def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]


async def test_engine_returns_questions_with_the_right_figure_ids():
    client = ScriptedGroq(
        [
            raw_item(),
            raw_item(
                text="In the figure shown, which stage is labelled 2?",
                answer="Condensation. Water vapour cools and turns into droplets.",
                figure_ref="F2",
            ),
        ]
    )
    engine = GenerationEngine(groq_client=client)
    questions, report = await engine.generate(make_request())
    assert [q.figure_id for q in questions] == [CELL.id, WATER.id]
    assert report.dropped_figure_invalid == 0


async def test_engine_drops_questions_that_contradict_the_metadata_and_retries():
    bad = raw_item(text="In the figure shown, what is the part labelled Q?")
    good = raw_item()
    good2 = raw_item(
        text="In the figure shown, which stage is labelled 3?",
        answer="Precipitation. Water falls as rain, hail or snow.",
        figure_ref="F2",
    )
    client = ScriptedGroq([bad, good2], [good])
    engine = GenerationEngine(groq_client=client)
    questions, report = await engine.generate(make_request())
    assert len(questions) == 2
    assert report.dropped_figure_invalid == 1
    # the rejection reason is fed back into the retry prompt
    assert "do not invent labels" in client.calls[1][1]


async def test_engine_gives_up_with_a_clear_error_when_every_question_is_invalid():
    client = ScriptedGroq([raw_item(figure_ref="F9")])
    engine = GenerationEngine(groq_client=client)
    with pytest.raises(GenerationValidationError) as exc:
        await engine.generate(make_request())
    assert "figure_ref" in json.dumps(exc.value.context)


# --- verifier sees the same description ---------------------------------


def test_verifier_prompts_carry_the_figure_description():
    req = make_request()
    q = build_question(raw_item(), req).question
    _, judge = build_judge_prompt([q])
    assert '"figure": "Caption: Plant cell' in judge
    assert "ground truth about the diagram" in judge

    mcq_req = make_request(type=QuestionType.MCQ, marks=1)
    mcq = build_question(
        {
            "text": "In the figure shown, which part is labelled A?",
            "options": ["Nucleus", "Cell wall", "Vacuole", "Ribosome"],
            "answer": "Nucleus",
            "explanation": "A is the nucleus.",
            "figure_ref": "F1",
        },
        mcq_req,
    ).question
    assert isinstance(mcq, Question)
    _, mcq_prompt = build_mcq_prompt([mcq])
    assert '"figure": "Caption: Plant cell' in mcq_prompt


def test_verifier_prompts_are_unchanged_without_figures():
    req = make_request(figures=None)
    q = build_question(raw_item(), req).question
    _, judge = build_judge_prompt([q])
    assert '"figure"' not in judge and "ground truth" not in judge
