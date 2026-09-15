"""
Covers the pieces the original suite never touched: difficulty scoring, the
syllabus index, and per-subject marks rules (test-plan.md Section 1, row
"Generate for each subject").
"""
import pytest

from generation_engine.difficulty import estimate_difficulty, flag_difficulty_mismatch
from generation_engine.prompts import build_prompt, supported_combinations
from generation_engine.schemas import (
    Difficulty,
    GenerationRequest,
    Question,
    QuestionType,
    Subject,
)
from generation_engine.subject_formats import get_marks_rule, get_prompt_note
from generation_engine.syllabus import SyllabusIndex
from generation_engine.validation import check_marks_format


def long_question(subject, answer, text="Describe the topic in detail."):
    return Question(
        subject=subject,
        chapter="Test Chapter",
        type=QuestionType.LONG,
        text=text,
        answer=answer,
        marks=5,
        difficulty=Difficulty.HARD,
    )


# --- difficulty ----------------------------------------------------------


def test_short_factual_answer_scores_easy():
    q = Question(
        subject=Subject.SCIENCE, chapter="Force", type=QuestionType.SHORT,
        text="What is the SI unit of force?", answer="Newton",
        marks=1, difficulty=Difficulty.EASY,
    )
    assert estimate_difficulty(q) == Difficulty.EASY


def test_long_analytical_answer_scores_hard():
    q = long_question(
        Subject.SOCIAL_SCIENCE,
        "1. Analyse the economic causes. 2. Evaluate the political effects. "
        "3. Compare the outcomes with earlier revolts. 4. Justify why the "
        "consequences reshaped the region, and therefore explain the result.",
        text="Analyse and evaluate the causes and effects of the revolt.",
    )
    assert estimate_difficulty(q) == Difficulty.HARD


def test_sharp_mismatch_is_flagged():
    q = Question(
        subject=Subject.SCIENCE, chapter="Force", type=QuestionType.SHORT,
        text="What is the SI unit of force?", answer="Newton",
        marks=1, difficulty=Difficulty.HARD,
    )
    assert flag_difficulty_mismatch(q) is not None


def test_adjacent_difficulty_is_not_flagged():
    q = Question(
        subject=Subject.SCIENCE, chapter="Force", type=QuestionType.SHORT,
        text="What is the SI unit of force?", answer="Newton",
        marks=1, difficulty=Difficulty.MEDIUM,
    )
    assert flag_difficulty_mismatch(q) is None


# --- subject-specific rules ---------------------------------------------


def test_math_5_mark_requires_working():
    bad = long_question(
        Subject.MATH,
        "1. The answer is found by looking at the graph carefully. "
        "2. It matches the expected value shown in the textbook diagram. "
        "3. The final value is twelve, which is the correct response overall.",
    )
    assert any("Math" in p for p in check_marks_format(bad))

    good = long_question(
        Subject.MATH,
        "1. Substitute the known values into the given equation carefully, "
        "writing each quantity with its correct sign. "
        "2. Simplify both sides step by step, collecting like terms until "
        "the variable x remains alone on the left hand side. "
        "3. Divide through by the coefficient of x to isolate it. "
        "4. Therefore x = 12, hence the required value is twelve.",
    )
    assert check_marks_format(good) == []


def test_social_science_5_mark_sections_count_as_points():
    q = long_question(
        Subject.SOCIAL_SCIENCE,
        "Causes: Heavy taxation burdened the peasants beyond what they could "
        "pay. The nobility held unfair privileges and paid almost nothing. "
        "Effects: The monarchy collapsed entirely within a few years. A new "
        "republic was declared as a direct result of the uprising, and the "
        "old feudal order was abolished across the country.",
    )
    assert check_marks_format(q) == []


@pytest.mark.parametrize("subject", list(Subject))
def test_every_subject_has_prompt_guidance(subject):
    assert get_prompt_note(subject).strip()


@pytest.mark.parametrize("subject", list(Subject))
@pytest.mark.parametrize("qtype,marks", supported_combinations())
def test_prompt_builds_for_every_subject_and_combination(subject, qtype, marks):
    req = GenerationRequest(
        subject=subject, chapter="Test Chapter", type=qtype,
        marks=marks, difficulty=Difficulty.MEDIUM, count=2,
    )
    system, user = build_prompt(req)
    assert system and subject.value in user
    assert "JSON array of exactly 2" in user


def test_kannada_length_bounds_are_relaxed():
    assert get_marks_rule(Subject.KANNADA, 2).max_words > get_marks_rule(
        Subject.SCIENCE, 2
    ).max_words


# --- syllabus ------------------------------------------------------------


def test_syllabus_lookup_is_normalized():
    idx = SyllabusIndex({Subject.SCIENCE: ["Chapter 3: Nutrition in Plants"]})
    assert idx.has_chapter(Subject.SCIENCE, "nutrition in plants")
    assert idx.has_chapter(Subject.SCIENCE, "Nutrition in Plants!")
    assert not idx.has_chapter(Subject.SCIENCE, "Algebra")


def test_syllabus_returns_canonical_name():
    idx = SyllabusIndex({Subject.MATH: ["Rational Numbers"]})
    assert idx.canonical_chapter(Subject.MATH, "rational numbers") == "Rational Numbers"
    assert idx.canonical_chapter(Subject.MATH, "nope") is None


def test_syllabus_from_dict_accepts_both_shapes():
    idx = SyllabusIndex.from_dict(
        {
            "Science": {"grade": 8, "chapters": ["Force and Pressure"]},
            "Math": ["Linear Equations"],
        }
    )
    assert len(idx) == 2
    assert idx.chapters(Subject.SCIENCE) == ["Force and Pressure"]


def test_syllabus_rejects_unknown_subject():
    with pytest.raises(ValueError):
        SyllabusIndex.from_dict({"Astrophysics": ["Black Holes"]})
