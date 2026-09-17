"""
Unit coverage for app/services/syllabus.py.

The API-level tests only ever exercise the "no syllabus configured" path
(chapter names accepted as given). These fill in the parts that only run
once a syllabus JSON file is actually loaded: normalisation of chapter
spelling, `seed_from_index`, and the loader's own error handling.
"""
from __future__ import annotations

import json

import pytest

from app.errors import NotFoundError
from app.services import syllabus as syllabus_service
from generation_engine.schemas import Subject as SubjectEnum
from generation_engine.syllabus import SyllabusIndex

@pytest.fixture(autouse=True)
def _reset_index():
    """Loader tests mutate the process-wide _syllabus_index; restore it."""
    original = syllabus_service.get_syllabus_index()
    yield
    syllabus_service._syllabus_index = original


# --- load_syllabus_index -------------------------------------------------


def test_load_syllabus_index_with_no_path_configured(monkeypatch):
    monkeypatch.setattr(syllabus_service.settings, "syllabus_json_path", None)
    assert syllabus_service.load_syllabus_index() is None
    assert syllabus_service.get_syllabus_index() is None


def test_load_syllabus_index_from_a_real_file(tmp_path, monkeypatch):
    data = {"Science": {"chapters": ["Nutrition in Plants", "Force and Pressure"]}}
    path = tmp_path / "syllabus.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(syllabus_service.settings, "syllabus_json_path", path)
    index = syllabus_service.load_syllabus_index()

    assert index is not None
    assert len(index) == 2
    assert syllabus_service.get_syllabus_index() is index


def test_load_syllabus_index_missing_file_is_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(
        syllabus_service.settings, "syllabus_json_path", tmp_path / "does-not-exist.json"
    )
    assert syllabus_service.load_syllabus_index() is None
    assert syllabus_service.get_syllabus_index() is None


def test_load_syllabus_index_invalid_json_is_not_fatal(tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(syllabus_service.settings, "syllabus_json_path", path)
    assert syllabus_service.load_syllabus_index() is None


def test_load_syllabus_index_unknown_subject_is_not_fatal(tmp_path, monkeypatch):
    path = tmp_path / "bad_subject.json"
    path.write_text(json.dumps({"NotASubject": ["x"]}), encoding="utf-8")
    monkeypatch.setattr(syllabus_service.settings, "syllabus_json_path", path)
    assert syllabus_service.load_syllabus_index() is None


# --- resolve_chapter with an index loaded ---------------------------------


@pytest.mark.asyncio
async def test_resolve_chapter_normalises_to_syllabus_spelling(db_session, monkeypatch):
    index = SyllabusIndex.from_dict(
        {"Science": {"chapters": ["Chapter 3: Photosynthesis in Plants"]}}
    )
    monkeypatch.setattr(syllabus_service, "_syllabus_index", index)

    chapter = await syllabus_service.resolve_chapter(
        db_session, SubjectEnum.SCIENCE, "photosynthesis in plants"
    )
    assert chapter.name == "Chapter 3: Photosynthesis in Plants"

    # A second, differently-punctuated call resolves to the same row.
    again = await syllabus_service.resolve_chapter(
        db_session, SubjectEnum.SCIENCE, "  PHOTOSYNTHESIS IN PLANTS!! "
    )
    assert again.id == chapter.id


@pytest.mark.asyncio
async def test_resolve_chapter_unrecognised_name_falls_back_to_stripped_input(
    db_session, monkeypatch
):
    index = SyllabusIndex.from_dict({"Science": {"chapters": ["Force and Pressure"]}})
    monkeypatch.setattr(syllabus_service, "_syllabus_index", index)

    chapter = await syllabus_service.resolve_chapter(
        db_session, SubjectEnum.SCIENCE, "  Some Unlisted Chapter  "
    )
    assert chapter.name == "Some Unlisted Chapter"


# --- find_chapter (read-only 404 paths) -----------------------------------


@pytest.mark.asyncio
async def test_find_chapter_404s_for_unknown_subject(db_session):
    with pytest.raises(NotFoundError):
        await syllabus_service.find_chapter(db_session, SubjectEnum.MATH, "Anything")


@pytest.mark.asyncio
async def test_find_chapter_404s_for_unknown_chapter(db_session):
    await syllabus_service.get_or_create_subject(db_session, SubjectEnum.SCIENCE)
    with pytest.raises(NotFoundError):
        await syllabus_service.find_chapter(db_session, SubjectEnum.SCIENCE, "Nope")


@pytest.mark.asyncio
async def test_find_chapter_returns_existing_row(db_session):
    chapter = await syllabus_service.resolve_chapter(
        db_session, SubjectEnum.SCIENCE, "Photosynthesis"
    )
    found = await syllabus_service.find_chapter(
        db_session, SubjectEnum.SCIENCE, "  photosynthesis  "
    )
    assert found.id == chapter.id


# --- seed_from_index -------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_from_index_creates_subjects_and_chapters(db_session):
    index = SyllabusIndex.from_dict(
        {
            "Science": {"chapters": ["Nutrition in Plants", "Force and Pressure"]},
            "Math": {"chapters": ["Rational Numbers"]},
        }
    )
    added = await syllabus_service.seed_from_index(db_session, index)
    assert added == 3

    rows = await syllabus_service.list_chapters(db_session, SubjectEnum.SCIENCE)
    names = {chapter.name for chapter, _count in rows}
    assert names == {"Nutrition in Plants", "Force and Pressure"}


@pytest.mark.asyncio
async def test_seed_from_index_is_idempotent(db_session):
    index = SyllabusIndex.from_dict({"Science": {"chapters": ["Nutrition in Plants"]}})
    first = await syllabus_service.seed_from_index(db_session, index)
    second = await syllabus_service.seed_from_index(db_session, index)
    assert first == 1
    assert second == 0
