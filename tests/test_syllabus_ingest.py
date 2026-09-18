"""
Tests for generation_engine/syllabus_ingest.py.

extract_chapters_from_pdf's PDF-reading glue is tested by monkeypatching
pypdf.PdfReader with a fake that returns canned per-page text — this tests
the page-range slicing and "no text layer" handling without needing a real
PDF file. Everything about *parsing* chapter lines out of text is tested
directly against extract_chapters_from_text, since that's where the actual
heuristic logic (and its edge cases) lives.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from generation_engine.schemas import Subject
from generation_engine.syllabus_ingest import (
    extract_chapters_from_pdf,
    extract_chapters_from_text,
    merge_chapters,
)

# --- extract_chapters_from_text: line-format coverage ----------------------


def test_dot_leader_toc_format():
    text = """
    Contents

    1. Nutrition in Plants .......... 1
    2. Nutrition in Animals .......... 12
    3. Fibre to Fabric .......... 24
    """
    assert extract_chapters_from_text(text) == [
        "Nutrition in Plants",
        "Nutrition in Animals",
        "Fibre to Fabric",
    ]


def test_whitespace_leader_toc_format():
    text = (
        "1. Nutrition in Plants          1\n"
        "2. Nutrition in Animals          12\n"
    )
    assert extract_chapters_from_text(text) == [
        "Nutrition in Plants",
        "Nutrition in Animals",
    ]


def test_no_punctuation_after_number_format():
    text = "1  Heat  45\n2  Acids, Bases and Salts  58\n"
    assert extract_chapters_from_text(text) == ["Heat", "Acids, Bases and Salts"]


def test_chapter_prefix_format():
    text = "Chapter 1: Nutrition in Plants\nChapter 2 - Nutrition in Animals\n"
    assert extract_chapters_from_text(text) == [
        "Nutrition in Plants",
        "Nutrition in Animals",
    ]


def test_unit_prefix_format_case_insensitive():
    text = "UNIT 1: Force and Pressure\nunit 2 Friction\n"
    assert extract_chapters_from_text(text) == ["Force and Pressure", "Friction"]


def test_bare_numbered_line_fallback():
    # No page number at all — the common shape on a chapter's own heading
    # page rather than a contents page.
    text = "1. Nutrition in Plants\n2. Nutrition in Animals\n"
    assert extract_chapters_from_text(text) == [
        "Nutrition in Plants",
        "Nutrition in Animals",
    ]


def test_mixed_formats_in_one_document():
    text = (
        "1. Nutrition in Plants .......... 1\n"
        "2  Nutrition in Animals  12\n"
        "Chapter 3: Fibre to Fabric\n"
    )
    assert extract_chapters_from_text(text) == [
        "Nutrition in Plants",
        "Nutrition in Animals",
        "Fibre to Fabric",
    ]


# --- non-chapter / noise filtering ------------------------------------------


@pytest.mark.parametrize(
    "title",
    ["Contents", "Index", "Answers", "Appendix", "Glossary", "Preface", "Bibliography"],
)
def test_front_and_back_matter_filtered_out(title):
    text = f"1. {title}\n2. Nutrition in Plants .......... 1\n"
    assert extract_chapters_from_text(text) == ["Nutrition in Plants"]


def test_blank_and_whitespace_lines_ignored():
    text = "\n\n   \n1. Nutrition in Plants .......... 1\n\n\n"
    assert extract_chapters_from_text(text) == ["Nutrition in Plants"]


def test_lines_with_no_letters_are_not_chapters():
    # A page-number-only line or a stray number shouldn't match as a title.
    text = "1. 42\n2. Nutrition in Plants .......... 1\n"
    assert extract_chapters_from_text(text) == ["Nutrition in Plants"]


def test_non_matching_prose_lines_are_ignored():
    text = (
        "This textbook covers the grade 8 Karnataka State Board syllabus.\n"
        "1. Nutrition in Plants .......... 1\n"
    )
    assert extract_chapters_from_text(text) == ["Nutrition in Plants"]


# --- deduplication -----------------------------------------------------------


def test_duplicate_titles_deduped_case_and_punctuation_insensitive():
    text = (
        "1. Nutrition in Plants .......... 1\n"
        "Chapter 1: NUTRITION IN PLANTS\n"  # same chapter, appears again on its own page
        "2. Nutrition in Animals .......... 12\n"
    )
    assert extract_chapters_from_text(text) == [
        "Nutrition in Plants",
        "Nutrition in Animals",
    ]


def test_empty_text_returns_empty_list():
    assert extract_chapters_from_text("") == []
    assert extract_chapters_from_text("   \n\n  ") == []


# --- extract_chapters_from_pdf: PDF-reading glue ----------------------------


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    def __init__(self, pages: list[str]):
        self.pages = [_FakePage(t) for t in pages]


@pytest.fixture
def fake_pdf(monkeypatch, tmp_path):
    """Monkeypatches pypdf.PdfReader; returns a factory(pages) -> Path that
    creates an (empty, content doesn't matter — the reader is faked) file at
    a real path, since extract_chapters_from_pdf checks the path exists."""
    import pypdf

    state = {}

    def fake_reader_ctor(path):
        return _FakeReader(state["pages"])

    monkeypatch.setattr(pypdf, "PdfReader", fake_reader_ctor)

    def factory(pages: list[str]) -> Path:
        state["pages"] = pages
        p = tmp_path / "textbook.pdf"
        p.write_bytes(b"%PDF-fake")
        return p

    return factory


def test_extract_from_pdf_scans_full_document_by_default(fake_pdf):
    path = fake_pdf(
        [
            "Contents\n",
            "1. Nutrition in Plants .......... 1\n2. Nutrition in Animals .......... 12\n",
        ]
    )
    assert extract_chapters_from_pdf(path) == [
        "Nutrition in Plants",
        "Nutrition in Animals",
    ]


def test_extract_from_pdf_respects_page_range(fake_pdf):
    path = fake_pdf(
        [
            "1. Nutrition in Plants .......... 1\n",  # page 1 — excluded below
            "2. Nutrition in Animals .......... 12\n",  # page 2 — included
        ]
    )
    assert extract_chapters_from_pdf(path, pages="2") == ["Nutrition in Animals"]


def test_extract_from_pdf_page_range_is_1_indexed_inclusive(fake_pdf):
    path = fake_pdf(["1. A .......... 1\n", "2. B .......... 2\n", "3. C .......... 3\n"])
    assert extract_chapters_from_pdf(path, pages="1-2") == ["A", "B"]


def test_extract_from_pdf_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_chapters_from_pdf("/nonexistent/path/to/textbook.pdf")


def test_extract_from_pdf_no_text_layer_raises(fake_pdf):
    path = fake_pdf(["", "", ""])  # scanned PDF: pypdf returns "" per page
    with pytest.raises(ValueError, match="no extractable text"):
        extract_chapters_from_pdf(path)


def test_extract_from_pdf_invalid_page_range_raises(fake_pdf):
    path = fake_pdf(["1. A .......... 1\n"])
    with pytest.raises(ValueError):
        extract_chapters_from_pdf(path, pages="5-2")  # end before start


# --- merge_chapters ----------------------------------------------------------


def test_merge_append_onto_empty_syllabus():
    updated, added, skipped = merge_chapters({}, Subject.SCIENCE, ["Heat", "Light"])
    assert updated["Science"]["chapters"] == ["Heat", "Light"]
    assert added == 2
    assert skipped == 0


def test_merge_append_onto_existing_subject():
    existing = {"Science": {"chapters": ["Heat"]}}
    updated, added, skipped = merge_chapters(existing, Subject.SCIENCE, ["Light", "Sound"])
    assert updated["Science"]["chapters"] == ["Heat", "Light", "Sound"]
    assert added == 2
    assert skipped == 0


def test_merge_append_dedupes_against_existing():
    existing = {"Science": {"chapters": ["Heat"]}}
    updated, added, skipped = merge_chapters(existing, Subject.SCIENCE, ["HEAT.", "Light"])
    assert updated["Science"]["chapters"] == ["Heat", "Light"]
    assert added == 1
    assert skipped == 1


def test_merge_replace_discards_existing_chapters():
    existing = {"Science": {"chapters": ["Heat", "Light"]}}
    updated, added, skipped = merge_chapters(
        existing, Subject.SCIENCE, ["Sound"], mode="replace"
    )
    assert updated["Science"]["chapters"] == ["Sound"]
    assert added == 1
    assert skipped == 0


def test_merge_leaves_other_subjects_untouched():
    existing = {"Math": {"chapters": ["Integers"]}, "Science": {"chapters": ["Heat"]}}
    updated, _, _ = merge_chapters(existing, Subject.SCIENCE, ["Light"])
    assert updated["Math"]["chapters"] == ["Integers"]
    assert updated["Science"]["chapters"] == ["Heat", "Light"]


def test_merge_does_not_mutate_input_dict():
    existing = {"Science": {"chapters": ["Heat"]}}
    merge_chapters(existing, Subject.SCIENCE, ["Light"])
    assert existing["Science"]["chapters"] == ["Heat"]  # unchanged


def test_merge_is_idempotent_when_run_twice():
    existing = {}
    once, _, _ = merge_chapters(existing, Subject.SCIENCE, ["Heat", "Light"])
    twice, added, skipped = merge_chapters(once, Subject.SCIENCE, ["Heat", "Light"])
    assert twice["Science"]["chapters"] == ["Heat", "Light"]
    assert added == 0
    assert skipped == 2


def test_merge_result_is_valid_syllabus_json_for_syllabusindex():
    """Round-trips through SyllabusIndex.from_dict, since that's the actual
    downstream consumer of whatever this writes to syllabus.json."""
    from generation_engine.syllabus import SyllabusIndex

    updated, _, _ = merge_chapters({}, Subject.SCIENCE, ["Heat", "Light"])
    index = SyllabusIndex.from_dict(updated)
    assert index.chapters(Subject.SCIENCE) == ["Heat", "Light"]


def test_merge_output_is_json_serializable():
    updated, _, _ = merge_chapters({}, Subject.SCIENCE, ["Heat"])
    json.dumps(updated)  # raises if not serializable
