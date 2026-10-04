"""
Fill in the blank and Match the following — the two question types added
beside MCQ / Short / Long. Covers the schema rules, how a Match question is
assembled from the model's ordered pairs, the format checks, the prompts,
the verifier's view of a Match key, and a full engine round trip. The Groq
call is stubbed throughout; nothing here hits the network.
"""
import pytest
from pydantic import ValidationError

from generation_engine.answer_verification import build_judge_prompt
from generation_engine.config import reload_settings
from generation_engine.engine import GenerationEngine
from generation_engine.prompts import build_prompt, supported_combinations
from generation_engine.rule_checks import check_answer_rules
from generation_engine.schemas import (
    Difficulty,
    GenerationRequest,
    Question,
    QuestionType,
    Subject,
    VALID_MARKS_BY_TYPE,
    count_blanks,
    match_left_items,
    parse_match_answer,
)
from generation_engine.validation import build_question, check_marks_format


@pytest.fixture(autouse=True)
def fresh_settings():
    reload_settings()
    yield
    reload_settings()


class StubGroq:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    async def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        if isinstance(payload, Exception):
            raise payload
        return payload


def make_request(q_type, marks, **overrides):
    base = dict(
        subject=Subject.SCIENCE,
        chapter="Force and Pressure",
        type=q_type,
        grade=8,
        marks=marks,
        difficulty=Difficulty.EASY,
        count=1,
    )
    base.update(overrides)
    return GenerationRequest(**base)


def make_question(q_type, marks, **fields):
    base = dict(
        subject=Subject.SCIENCE,
        chapter="Force and Pressure",
        type=q_type,
        grade=8,
        marks=marks,
        difficulty=Difficulty.EASY,
        text="",
        answer="",
    )
    base.update(fields)
    return Question(**base)


PAIRS_3 = [
    {"left": "Force", "right": "Newton"},
    {"left": "Pressure", "right": "Pascal"},
    {"left": "Work", "right": "Joule"},
]
PAIRS_5 = PAIRS_3 + [
    {"left": "Power", "right": "Watt"},
    {"left": "Frequency", "right": "Hertz"},
]


def match_raw(pairs=PAIRS_3, **extra):
    return {
        "text": "Match the quantities with their SI units:",
        "pairs": pairs,
        "topic": "Units",
        "tags": [],
        **extra,
    }


# --- the combinations --------------------------------------------------------


def test_new_types_are_registered_with_their_marks():
    assert VALID_MARKS_BY_TYPE[QuestionType.FILL] == {1}
    assert VALID_MARKS_BY_TYPE[QuestionType.MATCH] == {3, 5}
    combos = supported_combinations()
    assert (QuestionType.FILL, 1) in combos
    assert (QuestionType.MATCH, 3) in combos
    assert (QuestionType.MATCH, 5) in combos


def test_enum_values_are_the_strings_the_api_uses():
    assert QuestionType("Fill") is QuestionType.FILL
    assert QuestionType("Match") is QuestionType.MATCH


# --- Fill: schema ------------------------------------------------------------


def test_fill_with_one_blank_is_valid():
    q = make_question(
        QuestionType.FILL, 1,
        text="The green pigment in leaves is called _____.",
        answer="chlorophyll",
    )
    assert q.type == QuestionType.FILL


@pytest.mark.parametrize(
    "text",
    [
        "The green pigment in leaves is called chlorophyll.",  # no blank
        "The _____ pigment in _____ is green.",  # two blanks
    ],
)
def test_fill_needs_exactly_one_blank(text):
    with pytest.raises(ValidationError, match="exactly one blank"):
        make_question(QuestionType.FILL, 1, text=text, answer="x")


def test_fill_rejects_options_and_wrong_marks():
    with pytest.raises(ValidationError):
        make_question(
            QuestionType.FILL, 1, text="A _____ is a thing.", answer="x", options=["a", "b"]
        )
    with pytest.raises(ValidationError, match="marks"):
        make_question(QuestionType.FILL, 2, text="A _____ is a thing.", answer="x")


def test_blank_counter():
    assert count_blanks("one _____ here") == 1
    assert count_blanks("a __ b") == 0  # two underscores is not a blank
    assert count_blanks("_____ and ______") == 2


# --- Match: schema -----------------------------------------------------------

MATCH_TEXT = "Match the quantities with their units:\n1. Force\n2. Pressure\n3. Work"


def valid_match(**overrides):
    fields = dict(
        text=MATCH_TEXT,
        options=["Joule", "Newton", "Pascal"],
        answer="1-B, 2-C, 3-A",
    )
    fields.update(overrides)
    return make_question(QuestionType.MATCH, 3, **fields)


def test_valid_match_question():
    q = valid_match()
    assert q.options == ["Joule", "Newton", "Pascal"]


def test_match_helpers():
    assert match_left_items(MATCH_TEXT) == ["Force", "Pressure", "Work"]
    assert match_left_items("stem\n1. a\n3. c") == []  # gap in numbering
    assert parse_match_answer("1-B, 2-C, 3-A") == {1: "B", 2: "C", 3: "A"}
    assert parse_match_answer("1 - b; 2 : c; 3=a") == {1: "B", 2: "C", 3: "A"}
    assert parse_match_answer("1-B, 1-C") is None  # item matched twice
    assert parse_match_answer("1 goes with B because of units") is None


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"options": ["Joule", "Newton"]}, "exactly 3 options"),
        ({"options": ["Joule", "Joule", "Pascal"]}, "duplicates"),
        ({"options": None}, "exactly 3 options"),
        ({"text": "Match:\n1. Force\n2. Pressure"}, "3 numbered items"),
        ({"answer": "1-A, 2-A, 3-B"}, "different option letter"),  # letter reused
        ({"answer": "1-B, 2-C"}, "different option letter"),  # item missing
        ({"answer": "1-B, 2-C, 3-D"}, "different option letter"),  # letter out of range
        ({"answer": "Newton, Pascal, Joule"}, "pairs such as"),
    ],
)
def test_match_shape_is_enforced(overrides, message):
    with pytest.raises(ValidationError, match=message):
        valid_match(**overrides)


def test_match_marks_must_be_three_or_five():
    with pytest.raises(ValidationError):
        make_question(
            QuestionType.MATCH, 2,
            text="Match:\n1. a\n2. b", options=["x", "y"], answer="1-A, 2-B",
        )


# --- Match: assembled from the model's ordered pairs -------------------------


def option_for(question, number):
    """The Column B text the answer key sends item `number` to."""
    letter = parse_match_answer(question.answer)[number]
    return question.options["ABCDE".index(letter)]


@pytest.mark.parametrize("pairs,marks", [(PAIRS_3, 3), (PAIRS_5, 5)])
def test_build_match_question_key_matches_the_pairs(pairs, marks):
    result = build_question(match_raw(pairs), make_request(QuestionType.MATCH, marks))
    assert result.error is None, result.error
    q = result.question
    assert match_left_items(q.text) == [p["left"] for p in pairs]
    assert sorted(q.options) == sorted(p["right"] for p in pairs)
    for number, pair in enumerate(pairs, start=1):
        assert option_for(q, number) == pair["right"]


def test_match_column_b_is_not_left_in_answer_order():
    q = build_question(match_raw(PAIRS_5), make_request(QuestionType.MATCH, 5)).question
    assert q.options != [p["right"] for p in PAIRS_5]


def test_match_layout_is_stable_for_the_same_pairs():
    request = make_request(QuestionType.MATCH, 3)
    a = build_question(match_raw(), request).question
    b = build_question(match_raw(), request).question
    assert (a.text, a.options, a.answer) == (b.text, b.options, b.answer)


def test_model_numbering_and_a_made_up_answer_are_ignored():
    raw = match_raw(
        [
            {"left": "1. Force", "right": "(a) Newton"},
            {"left": "2. Pressure", "right": "(b) Pascal"},
            {"left": "3. Work", "right": "(c) Joule"},
        ],
        answer="1-A, 2-B, 3-C",
        options=["wrong", "wrong2", "wrong3"],
    )
    q = build_question(raw, make_request(QuestionType.MATCH, 3)).question
    assert match_left_items(q.text) == ["Force", "Pressure", "Work"]
    assert option_for(q, 1) == "Newton"
    assert "wrong" not in q.options


def test_match_uses_a_default_instruction_when_the_stem_is_missing_or_a_list_item():
    for stem in ("", "1. Force"):
        raw = match_raw()
        raw["text"] = stem
        q = build_question(raw, make_request(QuestionType.MATCH, 3)).question
        assert q.text.startswith("Match the items in Column A")


@pytest.mark.parametrize(
    "pairs,fragment",
    [
        (PAIRS_3[:2], "exactly 3 pairs"),
        (PAIRS_3 + [{"left": "Power", "right": "Watt"}], "exactly 3 pairs"),
        ([{"left": "Force", "right": "Newton"}, {"left": "force", "right": "Pascal"},
          {"left": "Work", "right": "Joule"}], "Column A items must be distinct"),
        ([{"left": "Force", "right": "Newton"}, {"left": "Pressure", "right": "newton"},
          {"left": "Work", "right": "Joule"}], "Column B items must be distinct"),
        ([{"left": "Force", "right": ""}, {"left": "Pressure", "right": "Pascal"},
          {"left": "Work", "right": "Joule"}], "non-empty"),
    ],
)
def test_bad_pairs_are_rejected(pairs, fragment):
    result = build_question(match_raw(pairs), make_request(QuestionType.MATCH, 3))
    assert result.question is None
    assert fragment in result.error


def test_pairs_must_be_a_list_of_objects():
    request = make_request(QuestionType.MATCH, 3)
    assert build_question({"text": "x"}, request).question is None
    assert build_question(match_raw(["Force-Newton"] * 3), request).question is None


# --- format checks -----------------------------------------------------------


def test_good_fill_passes_format_check():
    q = make_question(
        QuestionType.FILL, 1,
        text="The green pigment present in leaves is called _____.",
        answer="chlorophyll",
    )
    assert check_marks_format(q) == []


def test_fill_that_gives_away_its_answer_is_flagged():
    q = make_question(
        QuestionType.FILL, 1,
        text="Chlorophyll is the pigment called _____ in leaves.",
        answer="chlorophyll",
    )
    assert any("already contains" in p for p in check_marks_format(q))


def test_fill_with_almost_no_sentence_is_flagged():
    q = make_question(QuestionType.FILL, 1, text="Unit of force: _____", answer="newton")
    assert any("too little sentence" in p for p in check_marks_format(q))


def test_fill_answer_must_still_be_short():
    q = make_question(
        QuestionType.FILL, 1,
        text="Plants make their own food by the process of _____ using sunlight.",
        answer="a long process in which green plants prepare food using sunlight and water",
    )
    assert any("too long" in p for p in check_marks_format(q))


def test_good_match_passes_format_check():
    assert check_marks_format(valid_match()) == []


def test_match_with_long_items_or_an_explanation_is_flagged():
    long_item = "a very long description that goes on and on for far too many words to fit a column"
    q = valid_match(options=["Joule", long_item, "Pascal"])
    assert any("short phrases" in p for p in check_marks_format(q))
    q = valid_match(explanation="Because of the units.")
    assert any("explanation" in p for p in check_marks_format(q))


def test_five_mark_match_is_not_held_to_the_long_answer_word_count():
    pairs = PAIRS_5
    q = build_question(match_raw(pairs), make_request(QuestionType.MATCH, 5)).question
    assert check_marks_format(q) == []


# --- prompts -----------------------------------------------------------------


def test_fill_prompt_asks_for_a_single_blank():
    _, user = build_prompt(make_request(QuestionType.FILL, 1, count=4))
    assert "fill-in-the-blank" in user
    assert "exactly ONE blank" in user
    assert "_____" in user


def test_match_prompt_asks_for_ordered_pairs_for_the_marks_given():
    _, user = build_prompt(make_request(QuestionType.MATCH, 5, count=2))
    assert "exactly 5 pairs" in user
    assert '"pairs"' in user
    assert "Do not shuffle" in user
    # the model is not asked for the fields the system now writes
    assert '"options"' not in user and '"answer": "string' not in user


# --- verification ------------------------------------------------------------


def test_verifier_sees_column_b_for_a_match_question():
    _, user = build_judge_prompt([valid_match()])
    assert '"options": {"A": "Joule", "B": "Newton", "C": "Pascal"}' in user
    assert "match-the-following" in user


def test_verifier_prompt_for_other_types_is_unchanged():
    q = make_question(
        QuestionType.FILL, 1, text="The SI unit of force is _____ always.", answer="newton"
    )
    _, user = build_judge_prompt([q])
    assert "options" not in user
    assert "match-the-following" not in user


def test_arithmetic_rules_leave_match_questions_alone():
    assert check_answer_rules(valid_match()).outcome == "na"


# --- full engine round trip --------------------------------------------------


@pytest.mark.asyncio
async def test_engine_generates_fill_questions():
    payload = [
        {"text": "The green pigment present in leaves is called _____.",
         "answer": "chlorophyll", "explanation": "", "topic": "Pigments", "tags": []},
        {"text": "Plants release _____ gas during photosynthesis into the air.",
         "answer": "oxygen", "explanation": "", "topic": "Gases", "tags": []},
    ]
    engine = GenerationEngine(groq_client=StubGroq(payload))
    questions, report = await engine.generate(make_request(QuestionType.FILL, 1, count=2))
    assert [q.type for q in questions] == [QuestionType.FILL] * 2
    assert [q.answer for q in questions] == ["chlorophyll", "oxygen"]
    assert report.returned_count == 2


@pytest.mark.asyncio
async def test_engine_generates_match_questions_and_retries_a_bad_one():
    bad = match_raw(PAIRS_3[:2])  # two pairs where three are needed
    good = match_raw(PAIRS_3)
    stub = StubGroq([bad], [good])
    engine = GenerationEngine(groq_client=stub)
    questions, report = await engine.generate(make_request(QuestionType.MATCH, 3, count=1))

    assert len(questions) == 1
    assert report.dropped_schema_invalid == 1
    assert report.attempts == 2
    q = questions[0]
    assert q.type == QuestionType.MATCH and q.marks == 3
    assert len(q.options) == 3
    # the retry prompt told the model what was wrong
    assert "exactly 3 pairs" in stub.calls[1][1]
