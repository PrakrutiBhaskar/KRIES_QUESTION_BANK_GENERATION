"""Hindi (Class 7, third language) as a sixth subject."""
from pathlib import Path

import pytest

from generation_engine.schemas import Subject
from generation_engine.subject_formats import get_marks_rule, get_prompt_note
from generation_engine.syllabus import SyllabusIndex, _normalize_chapter

SYLLABUS_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "syllabus.json"
H = Subject.HINDI


@pytest.fixture(scope="module")
def index():
    return SyllabusIndex.from_json(SYLLABUS_PATH, strict_grades=True)


def test_hindi_is_a_subject():
    assert H.value == "Hindi"
    assert Subject("Hindi") is H


def test_hindi_grade7_lessons_come_from_the_contents_pages(index):
    assert index.grades(H) == [7, 8, 9]
    chapters = index.chapters(H, grade=7)
    assert len(chapters) == 19
    # bridge lesson first, supplementary reading last, both Ginti lessons present
    assert chapters[0] == "\u0938\u0947\u0924\u0941\u092c\u0902\u0927"
    assert chapters[-1] == "\u092a\u0942\u0930\u0915 \u0935\u093e\u091a\u0928"
    assert "\u0917\u093f\u0928\u0924\u0940 (50-70)" in chapters
    assert "\u0917\u093f\u0928\u0924\u0940 (71-100)" in chapters


def test_hindi_grade8_lessons_are_scoped_to_grade_8(index):
    chapters = index.chapters(H, grade=8)
    assert len(chapters) == 18
    assert chapters[0] == "\u0938\u0947\u0924\u0941\u092c\u0902\u0927"
    assert chapters[-1] == "\u0915\u092c\u0940\u0930 \u0915\u0947 \u0926\u094b\u0939\u0947"
    # grade 7 lessons are not grade 8 lessons, and vice versa
    assert not index.has_chapter(H, "\u0926\u093f\u0932\u094d\u0932\u0940", grade=8)
    assert index.has_chapter(H, "\u0926\u093f\u0932\u094d\u0932\u0940", grade=7)
    assert not index.has_chapter(H, "\u0915\u092c\u0940\u0930 \u0915\u0947 \u0926\u094b\u0939\u0947", grade=7)


def test_setubandh_bridge_lesson_is_in_every_grade(index):
    name = "\u0938\u0947\u0924\u0941\u092c\u0902\u0927"
    assert index.grades_for_chapter(H, name) == [7, 8, 9]


def test_hindi_grade9_lessons_are_scoped_to_grade_9(index):
    chapters = index.chapters(H, grade=9)
    assert len(chapters) == 21
    assert chapters[1] == "\u091c\u092f-\u091c\u092f \u092d\u093e\u0930\u0924 \u092e\u093e\u0924\u093e"
    assert index.has_chapter(H, "\u0930\u0939\u0940\u092e \u0915\u0947 \u0926\u094b\u0939\u0947", grade=9)
    assert not index.has_chapter(H, "\u0930\u0939\u0940\u092e \u0915\u0947 \u0926\u094b\u0939\u0947", grade=8)
    # the Parishisht divider is not a lesson
    assert not index.has_chapter(H, "\u092a\u0930\u093f\u0936\u093f\u0937\u094d\u091f - 1", grade=9)


def test_appendix_sections_are_listed_once_per_grade(index):
    chapters = index.chapters(H, grade=9)
    assert len(chapters) == len(set(chapters))
    assert "\u092a\u0924\u094d\u0930 \u0932\u0947\u0916\u0928" in chapters


def test_nukta_letters_match_whether_precomposed_or_decomposed(index):
    assert _normalize_chapter("\u0928\u0920\u095e\u0947") == _normalize_chapter("\u0928\u0920\u092b\u093c\u0947")
    assert index.has_chapter(H, "\u0928\u095e\u0947 \u0915\u0947 \u091a\u0915\u094d\u0915\u0930 \u092e\u0947\u0902", grade=9)


def test_devanagari_titles_keep_their_vowel_signs():
    # Without the Devanagari block in the keep-list, matras/viramas are stripped
    # and distinct titles collapse into the same key.
    a = _normalize_chapter("\u0926\u093f\u0932\u094d\u0932\u0940")
    b = _normalize_chapter("\u0926\u0932\u0932")
    assert a != b
    assert "\u093f" in a and "\u094d" in a


def test_hindi_prompt_note_asks_for_devanagari():
    note = get_prompt_note(H)
    assert "Devanagari" in note and "Hindi" in note


def test_hindi_length_bounds_are_relaxed_for_a_third_language():
    assert get_marks_rule(H, 2).min_words < get_marks_rule(Subject.SCIENCE, 2).min_words
    assert get_marks_rule(H, 5).min_words < get_marks_rule(Subject.SCIENCE, 5).min_words
    assert get_marks_rule(H, 1).forbid_explanation
