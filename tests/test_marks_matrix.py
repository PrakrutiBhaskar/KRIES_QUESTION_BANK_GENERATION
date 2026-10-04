"""Every logically possible (type, marks) pair is accepted end to end; nothing else is."""
import pytest

from generation_engine import GenerationRequest, validate_request_combination
from generation_engine.prompts import build_prompt, supported_combinations
from generation_engine.schemas import (
    VALID_MARKS,
    VALID_MARKS_BY_TYPE,
    Difficulty,
    QuestionType,
    Subject,
)

ALL = [(t, m) for t in QuestionType for m in sorted(VALID_MARKS)]
VALID = [(t, m) for t, ms in VALID_MARKS_BY_TYPE.items() for m in sorted(ms)]
INVALID = [c for c in ALL if c not in VALID]


def req(t, m):
    return GenerationRequest(
        subject=Subject.SCIENCE, chapter="Nutrition in Plants", type=t, grade=8,
        marks=m, difficulty=Difficulty.MEDIUM, count=3,
    )


def test_the_matrix_is_exactly_what_the_format_allows():
    assert VALID_MARKS_BY_TYPE == {
        QuestionType.MCQ: {1, 2, 3, 5},
        QuestionType.SHORT: {1, 2, 3},
        QuestionType.LONG: {3, 5},
        QuestionType.FILL: {1, 2, 3, 5},
        QuestionType.MATCH: {3, 5},
    }


def test_every_valid_combination_has_a_prompt_template():
    assert set(supported_combinations()) == set(VALID)


@pytest.mark.parametrize("t,m", VALID)
def test_valid_combinations_validate_and_build_a_prompt(t, m):
    assert validate_request_combination(req(t, m)) == []
    system, user = build_prompt(req(t, m))
    assert user and system


@pytest.mark.parametrize("t,m", [c for c in VALID if c[0] in (QuestionType.MCQ, QuestionType.FILL) and c[1] > 1])
def test_heavier_single_pick_questions_are_asked_to_be_more_demanding(t, m):
    _, user = build_prompt(req(t, m))
    assert f"worth {m} marks" in user


@pytest.mark.parametrize("t,m", INVALID)
def test_impossible_combinations_are_rejected(t, m):
    assert validate_request_combination(req(t, m))
