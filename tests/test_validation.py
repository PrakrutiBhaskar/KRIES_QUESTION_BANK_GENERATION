import pytest

from generation_engine.schemas import Question, GenerationRequest, Subject, QuestionType, Difficulty
from generation_engine.validation import (
    validate_request_combination,
    check_marks_format,
    find_duplicates,
    build_question,
)


def make_short(marks, answer, subject=Subject.SCIENCE, text="Why does ice float on water?"):
    return Question(
        subject=subject,
        chapter="States of Matter",
        type=QuestionType.SHORT if marks in (1, 2, 3) else QuestionType.LONG,
        text=text,
        answer=answer,
        marks=marks,
        difficulty=Difficulty.MEDIUM,
    )


# --- request combination checks -------------------------------------------------

def test_mcq_must_request_1_mark():
    req = GenerationRequest(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=QuestionType.MCQ,
        marks=3, difficulty=Difficulty.EASY, count=5,
    )
    problems = validate_request_combination(req)
    assert problems


def test_valid_combination_has_no_problems():
    req = GenerationRequest(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=QuestionType.MCQ,
        marks=1, difficulty=Difficulty.EASY, count=5,
    )
    assert validate_request_combination(req) == []


def test_count_exceeding_max_is_rejected():
    req = GenerationRequest(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=QuestionType.SHORT,
        marks=2, difficulty=Difficulty.EASY, count=25,
    )
    # bump count past the configured max via model_copy to bypass the 1-25 field bound
    req = req.model_copy(update={"count": 999})
    assert validate_request_combination(req)


# --- marks-vs-answer-length checks ----------------------------------------------

def test_mcq_marks_format_passes():
    q = Question(
        subject=Subject.SCIENCE, chapter="Force", type=QuestionType.MCQ,
        text="What is the SI unit of force?", options=["Newton", "Joule", "Watt", "Pascal"],
        answer="Newton", explanation="It is the SI unit of force, named after Isaac Newton.",
        marks=1, difficulty=Difficulty.EASY,
    )
    assert check_marks_format(q) == []


def test_1_mark_descriptive_accepts_one_line_answer():
    q = make_short(1, "Newton")
    assert check_marks_format(q) == []


def test_1_mark_rejects_long_answer():
    q = make_short(1, "Force is measured in newtons because a newton is defined as "
                      "the force needed to accelerate one kilogram by one metre per second squared.")
    problems = check_marks_format(q)
    assert any("1-mark" in p for p in problems)


def test_1_mark_rejects_explanation():
    q = Question(
        subject=Subject.SCIENCE, chapter="Force", type=QuestionType.SHORT,
        text="What is the SI unit of force?", answer="Newton",
        explanation="Named after Isaac Newton.", marks=1, difficulty=Difficulty.EASY,
    )
    assert any("explanation" in p for p in check_marks_format(q))


def test_2_mark_rejects_three_points():
    q = make_short(2, "Point one. Point two. Point three.")
    problems = check_marks_format(q)
    assert any("2-mark" in p for p in problems)


def test_2_mark_accepts_one_or_two_lines():
    q = make_short(2, "Ice floats because it is less dense than liquid water, due to hydrogen bonding.")
    assert check_marks_format(q) == []


def test_3_mark_requires_exactly_three_points():
    q = make_short(3, "1. First point. 2. Second point.")
    problems = check_marks_format(q)
    assert any("3-mark" in p for p in problems)


def test_3_mark_passes_with_three_points():
    q = make_short(3, "1. First point. 2. Second point. 3. Third point.")
    assert check_marks_format(q) == []


def test_5_mark_requires_multiple_points_and_length():
    q = make_short(5, "Short answer.")
    problems = check_marks_format(q)
    assert problems


def test_5_mark_math_flags_missing_derivation_language():
    long_answer = "This is a fairly long answer with several words to pass length checks. " * 3
    q = make_short(5, long_answer, subject=Subject.MATH, text="Solve the quadratic equation.")
    problems = check_marks_format(q)
    assert any("step" in p.lower() or "derivation" in p.lower() for p in problems)


def test_5_mark_social_science_requires_cause_effect_language():
    long_answer = "This is a fairly long answer with several words to pass length checks. " * 3
    q = make_short(5, long_answer, subject=Subject.SOCIAL_SCIENCE, text="Discuss the French Revolution.")
    problems = check_marks_format(q)
    assert any("causes/effects" in p for p in problems)


# --- duplicate detection ---------------------------------------------------------

def test_exact_duplicate_detected():
    q1 = make_short(2, "Ice floats because it is less dense than water.", text="Why does ice float?")
    q2 = make_short(2, "A different answer here.", text="Why does ice float?")
    dups = find_duplicates([q1, q2])
    assert dups == {1}


def test_near_duplicate_detected():
    q1 = make_short(2, "answer", text="Explain why plants need sunlight for photosynthesis.")
    q2 = make_short(2, "answer", text="Explain why plants need sunlight for photosynthesis to occur.")
    dups = find_duplicates([q1, q2], similarity_threshold=0.85)
    assert dups == {1}


def test_distinct_questions_not_flagged():
    q1 = make_short(2, "answer", text="Why does ice float on water?")
    q2 = make_short(2, "answer", text="Explain the process of respiration in humans.")
    assert find_duplicates([q1, q2]) == set()


# --- schema build from raw LLM dicts ---------------------------------------------

def test_build_question_from_valid_raw():
    req = GenerationRequest(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=QuestionType.MCQ,
        marks=1, difficulty=Difficulty.EASY, count=1,
    )
    raw = {
        "text": "What gas do plants absorb during photosynthesis?",
        "options": ["Oxygen", "Carbon dioxide", "Nitrogen", "Hydrogen"],
        "answer": "Carbon dioxide",
        "explanation": "Plants absorb CO2 for photosynthesis.",
        "topic": "Gas exchange",
        "tags": ["photosynthesis"],
    }
    result = build_question(raw, req)
    assert result.error is None
    assert result.question.subject == Subject.SCIENCE


def test_build_question_from_invalid_raw():
    req = GenerationRequest(
        subject=Subject.SCIENCE, chapter="Photosynthesis", type=QuestionType.MCQ,
        marks=1, difficulty=Difficulty.EASY, count=1,
    )
    raw = {"text": "Missing options and answer"}
    result = build_question(raw, req)
    assert result.error is not None
    assert result.question is None
