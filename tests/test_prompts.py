import pytest

from generation_engine.schemas import GenerationRequest, Subject, QuestionType, Difficulty
from generation_engine.prompts import build_prompt


def make_request(**overrides):
    base = dict(
        subject=Subject.MATH,
        chapter="Quadratic Equations",
        type=QuestionType.LONG,
        grade=8,
        marks=5,
        difficulty=Difficulty.MEDIUM,
        count=3,
    )
    base.update(overrides)
    return GenerationRequest(**base)


def test_mcq_prompt_mentions_4_options():
    req = make_request(subject=Subject.SCIENCE, type=QuestionType.MCQ, marks=1)
    system, user = build_prompt(req)
    assert "4 options" in user
    assert "justification" in user


@pytest.mark.parametrize("grade", [7, 8, 9])
def test_prompt_mentions_the_requested_grade(grade):
    req = make_request(grade=grade)
    _, user = build_prompt(req)
    assert f"Class {grade}" in user


def test_different_grades_produce_different_prompts():
    req_7 = make_request(grade=7)
    req_9 = make_request(grade=9)
    _, user_7 = build_prompt(req_7)
    _, user_9 = build_prompt(req_9)
    assert user_7 != user_9
    assert "Class 7" in user_7 and "Class 7" not in user_9
    assert "Class 9" in user_9 and "Class 9" not in user_7


def test_short_2_mark_prompt_mentions_one_two_lines():
    req = make_request(type=QuestionType.SHORT, marks=2)
    _, user = build_prompt(req)
    assert "1-2 lines" in user


def test_short_3_mark_prompt_mentions_exactly_three():
    req = make_request(type=QuestionType.SHORT, marks=3)
    _, user = build_prompt(req)
    assert "EXACTLY 3" in user


def test_long_5_mark_math_prompt_includes_subject_note():
    req = make_request(subject=Subject.MATH, type=QuestionType.LONG, marks=5)
    _, user = build_prompt(req)
    assert "derivation" in user.lower()


def test_long_5_mark_social_science_prompt_includes_causes_effects_note():
    req = make_request(subject=Subject.SOCIAL_SCIENCE, type=QuestionType.LONG, marks=5)
    _, user = build_prompt(req)
    assert "causes" in user.lower() or "effects" in user.lower()


def test_prompt_requests_exact_count():
    req = make_request(count=7, type=QuestionType.LONG, marks=5)
    _, user = build_prompt(req)
    assert "exactly 7" in user


def test_prompt_includes_topic_hint_when_present():
    req = make_request(type=QuestionType.SHORT, marks=2, topic="Photosynthesis basics")
    _, user = build_prompt(req)
    assert "Photosynthesis basics" in user


def test_unsupported_combination_raises_keyerror():
    req = GenerationRequest(
        subject=Subject.MATH, chapter="Algebra", type=QuestionType.SHORT,
        grade=8, marks=2, difficulty=Difficulty.EASY, count=1,
    )
    # tamper with marks post-validation to simulate an unsupported combo reaching build_prompt
    tampered = req.model_copy(update={"marks": 4})
    with pytest.raises(KeyError):
        build_prompt(tampered)
