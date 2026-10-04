"""Strict Karnataka State Board scoping: grade-aware chapters, topics, scope guard."""
import json
from pathlib import Path

import pytest

from generation_engine import (
    GenerationEngine,
    GenerationRequest,
    InvalidRequestError,
    Subject,
    QuestionType,
    Difficulty,
    SyllabusIndex,
)
from generation_engine.config import settings
from generation_engine.prompts import build_prompt
from generation_engine.schemas import Question
from generation_engine.validation import check_board_scope, validate_request_combination

SYLLABUS_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "syllabus.json"


def req(**kw):
    base = dict(
        subject=Subject.MATH, chapter="Integers", type=QuestionType.SHORT,
        grade=7, marks=2, difficulty=Difficulty.EASY, count=1,
    )
    base.update(kw)
    return GenerationRequest(**base)


@pytest.fixture(scope="module")
def index():
    return SyllabusIndex.from_json(SYLLABUS_PATH)


def test_shipped_syllabus_loads_and_ignores_meta(index):
    assert Subject.MATH in index.subjects()
    assert index.is_grade_scoped(Subject.MATH)
    assert index.grades(Subject.MATH) == [7, 8, 9]


def test_chapter_accepted_only_for_its_own_grade(index):
    assert validate_request_combination(req(chapter="Integers", grade=7), index) == []
    problems = validate_request_combination(req(chapter="Integers", grade=9), index)
    assert problems and "Class 9" in problems[0] and "Class 7" in problems[0]


def test_unknown_chapter_still_rejected(index):
    problems = validate_request_combination(req(chapter="Quantum Chromodynamics"), index)
    assert problems and "unknown chapter" in problems[0]


def test_grade_lists_are_disjoint_where_expected(index):
    assert index.has_chapter(Subject.MATH, "Probability", grade=9)
    assert not index.has_chapter(Subject.MATH, "Probability", grade=7)
    assert index.chapters(Subject.MATH, grade=9)[0] == "Number Systems"


def test_ungraded_subject_accepts_any_grade():
    idx = SyllabusIndex({Subject.ENGLISH: ["Tenses"]})
    assert not idx.is_grade_scoped(Subject.ENGLISH)
    assert idx.has_chapter(Subject.ENGLISH, "tenses", grade=8)


def test_from_dict_derives_union_from_grades_and_reads_topics():
    idx = SyllabusIndex.from_dict({
        "Science": {
            "grades": {"7": ["Heat"], "8": ["Sound"]},
            "topics": {"Heat": ["Conduction", "Convection"]},
        }
    })
    assert idx.chapters(Subject.SCIENCE) == ["Heat", "Sound"]
    assert idx.topics(Subject.SCIENCE, "heat") == ["Conduction", "Convection"]
    assert idx.topics(Subject.SCIENCE, "Sound") == []


def test_require_syllabus_blocks_unverifiable_requests():
    assert validate_request_combination(req(), None) == []
    problems = validate_request_combination(req(), None, require_syllabus=True)
    assert problems and "syllabus" in problems[0]


def test_prompt_pins_board_grade_chapter_and_topics():
    system, user = build_prompt(req(), chapter_topics=["Number line", "Addition of integers"])
    assert "Karnataka State Board" in system and "KTBS" in system
    assert "Class 7" in user and '"Integers"' in user
    assert "Number line; Addition of integers" in user
    assert "other boards" in user


def test_prompt_omits_topic_list_when_caller_narrowed_topic():
    _, user = build_prompt(req(topic="Number line"), chapter_topics=["A", "B"])
    assert "A; B" not in user and "Number line" in user


@pytest.mark.parametrize("text", ["As per the NCERT book, define a prime.", "In CBSE exams, what is..."])
def test_board_scope_guard_flags_other_boards(text):
    q = Question(
        subject=Subject.MATH, chapter="Integers", type=QuestionType.SHORT, grade=7,
        text=text, answer="A prime has exactly two factors.", marks=2,
        difficulty=Difficulty.EASY,
    )
    assert check_board_scope(q)


def test_board_scope_guard_passes_normal_question():
    q = Question(
        subject=Subject.MATH, chapter="Integers", type=QuestionType.SHORT, grade=7,
        text="What is -5 + 3?", answer="-2", marks=2, difficulty=Difficulty.EASY,
    )
    assert check_board_scope(q) == []


@pytest.mark.asyncio
async def test_engine_rejects_wrong_grade_chapter_with_400(index):
    class NoCall:
        async def complete_json(self, *a, **k):
            raise AssertionError("Groq must not be called for an out-of-syllabus request")

    engine = GenerationEngine(groq_client=NoCall(), syllabus=index)
    with pytest.raises(InvalidRequestError):
        await engine.generate(req(chapter="Probability", grade=7))


def test_require_syllabus_setting_defaults_off():
    assert settings.require_syllabus is False


# --- Kannada (first language) lesson lists from the KTBS contents pages ---

def test_kannada_lessons_are_scoped_to_their_grade(index):
    K = Subject.KANNADA
    assert index.grades(K) == [7, 8, 9]
    assert [len(index.chapters(K, grade=g)) for g in (7, 8, 9)] == [21, 22, 22]
    assert index.has_chapter(K, "ಹುತ್ತರಿ ಹಾಡು", grade=7)
    assert not index.has_chapter(K, "ಹುತ್ತರಿ ಹಾಡು", grade=8)
    assert index.has_chapter(K, "ಮಗ್ಗದ ಸಾಹೇಬ", grade=8)
    assert index.has_chapter(K, "ಅಧಿಕಾರ", grade=9)


def test_kannada_title_matching_ignores_zwnj_and_keeps_vowel_signs(index):
    K = Subject.KANNADA
    assert index.has_chapter(K, "ಹಿಲ್ಪನ್ಹೆಡ್ ಚಳವಳಿ", grade=7)  # typed without the ZWNJ
    # titles that differ only by vowel signs must stay distinct
    assert index.canonical_chapter(K, "ಅಮ್ಮ", grade=8) == "ಅಮ್ಮ"
    assert not index.has_chapter(K, "ಅಮ", grade=8)


# --- strict grades: a chapter lives only in the grade(s) that name it ---

def test_strict_index_gives_unscoped_subject_no_chapters_in_any_grade():
    idx = SyllabusIndex.from_dict({"English": {"chapters": ["Tenses"]}}, strict_grades=True)
    assert idx.chapters(Subject.ENGLISH, grade=8) == []
    assert not idx.has_chapter(Subject.ENGLISH, "Tenses", grade=8)


def test_shipped_syllabus_strict_has_no_grade_leakage(index):
    strict = SyllabusIndex.from_json(SYLLABUS_PATH, strict_grades=True)
    for subject in strict.subjects():
        for g in (7, 8, 9):
            for ch in strict.chapters(subject, grade=g):
                assert strict.has_chapter(subject, ch, grade=g)
                other = [x for x in (7, 8, 9) if x != g]
                # a chapter listed for g may only also be listed for another grade if
                # that grade's own list names it (shared textbook titles like Data Handling)
                for o in other:
                    assert strict.has_chapter(subject, ch, grade=o) == (
                        o in strict.grades_for_chapter(subject, ch)
                    )
    # English is grade-scoped by its textbook lessons (Class 7 has 19), not empty.
    assert len(strict.chapters(Subject.ENGLISH, grade=7)) == 19
    assert not strict.has_chapter(Subject.ENGLISH, "A Tiger in the House", grade=8)
    assert not strict.has_chapter(Subject.KANNADA, "ಮಗ್ಗದ ಸಾಹೇಬ", grade=7)


# --- Science lists from the KTBS contents pages ---

def test_science_chapters_are_in_their_own_grade_only(index):
    S = Subject.SCIENCE
    assert [len(index.chapters(S, grade=g)) for g in (7, 8, 9)] == [12, 13, 12]
    assert index.has_chapter(S, "Heat Transfer in Nature", grade=7)
    assert not index.has_chapter(S, "Heat Transfer in Nature", grade=8)
    assert index.has_chapter(S, "Exploring Forces", grade=8)
    assert not index.has_chapter(S, "Exploring Forces", grade=9)
    assert index.has_chapter(S, "Is Matter Around Us Pure?", grade=9)
    assert index.has_chapter(S, "is matter around us pure", grade=9)  # punctuation-insensitive
    # old interim chapters that are not in the KTBS books are gone
    assert not index.has_chapter(S, "Diversity in Living Organisms")
    assert not index.has_chapter(S, "Natural Resources")


# --- Social Science lists from the KTBS contents pages ---

def test_social_science_chapters_are_in_their_own_grade_only(index):
    SS = Subject.SOCIAL_SCIENCE
    assert [len(index.chapters(SS, grade=g)) for g in (7, 8, 9)] == [27, 30, 33]
    assert index.has_chapter(SS, "The Advent of Europeans to India", grade=7)
    assert not index.has_chapter(SS, "The Advent of Europeans to India", grade=8)
    assert index.has_chapter(SS, "Lithosphere", grade=8)
    assert not index.has_chapter(SS, "Lithosphere", grade=9)
    assert index.has_chapter(SS, "Our Constitution", grade=9)
    assert not index.has_chapter(SS, "Our Constitution", grade=7)
    # punctuation/case-insensitive
    assert index.has_chapter(SS, "india in the 18th century 1707  1757", grade=7)
    for a in (7, 8, 9):
        for b in (7, 8, 9):
            if a < b:
                assert not set(map(str.lower, index.chapters(SS, grade=a))) & set(
                    map(str.lower, index.chapters(SS, grade=b))
                )


# --- English lists from the KTBS contents pages only ---

def test_english_has_only_the_textbook_lessons_for_each_grade(index):
    E = Subject.ENGLISH
    assert index.is_grade_scoped(E)
    assert [len(index.chapters(E, grade=g)) for g in (7, 8, 9)] == [19, 22, 24]
    assert index.has_chapter(E, "A Tiger in the House", grade=7)
    assert not index.has_chapter(E, "A Tiger in the House", grade=8)
    assert index.has_chapter(E, "The Heavenly Parasol", grade=8)
    assert not index.has_chapter(E, "The Heavenly Parasol", grade=9)
    assert index.has_chapter(E, "An Astrologer's Day", grade=9)
    assert index.has_chapter(E, "Letter Writing & Determiners", grade=9)
    assert not index.has_chapter(E, "Letter Writing & Determiners", grade=7)
    # topics that are not printed in the textbook contents are not in the syllabus
    for g in (7, 8, 9):
        for extra in ("Grammar: Parts of Speech", "Essay Writing", "Precis Writing", "Report Writing"):
            assert not index.has_chapter(E, extra, grade=g)
