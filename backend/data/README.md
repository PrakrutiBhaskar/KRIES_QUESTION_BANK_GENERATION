# `syllabus.json`

Interim, manually-curated chapter list for grades 7–9 (Karnataka State
Board), spanning all three grades per subject rather than split by grade.

This exists to unblock the frontend's subject/chapter selector before the
real PDF-parsing pipeline (`docs/task-tracker.md`, `spec.md` Section 8)
lands — without it, `GET /subjects/{subject}/chapters` returns `[]` for
every subject until someone happens to generate a question for a chapter
first, which makes a dropdown-style chapter picker impossible to populate
on a fresh install.

Treat these chapter names as a reasonable starting point, not a
verified-against-the-textbook source of truth. Swap this file out (or
extend it) once real syllabus data is parsed from the actual textbooks.

Loaded via the `SYLLABUS_JSON_PATH` setting in `backend/.env`. Shape is
defined by `generation_engine/syllabus.py`'s `SyllabusIndex.from_json`.

## Kannada chapters (Grades 7–9)

The `Kannada` entry lists the **Gadya Bhaga (prose)** and **Padya Bhaga
(poetry)** lessons of the KTBS *Siri Kannada* (First Language) textbooks —
8 prose + 8 poetry lessons per grade, named `Gadya: <lesson>` /
`Padya: <lesson>` (romanised, like the rest of this file). Each grade's list
also includes the shared umbrella / grammar / writing chapters, so the grade
filter still returns them.

Not included: *Pathya Puraka Adhyayana* (supplementary readers), and the
*Tili Kannada* (2nd language) and *Nudi Kannada* (3rd language) textbooks.
Lesson titles were compiled from third-party KTBS study sites, not the
official PDFs — verify against the current textbook edition before relying
on them.

## Strict Karnataka State Board enforcement

The engine treats this file as the allow-list. A request is rejected (HTTP 400)
unless its chapter is in the requested **grade's** list for that subject, and
the prompt tells the model to stay inside that chapter of the KTBS textbook.

- `grades` -> enforced per grade. Subjects without it (currently **English**)
  can't be grade-checked: any listed chapter is accepted for any grade.
- `topics` (optional, `{chapter: [sub-topics]}`) -> injected into the prompt to
  bound each chapter's scope.
- `_meta` -> provenance; ignored by the loader.
- `REQUIRE_SYLLABUS=true` (engine/backend env) refuses generation when no
  syllabus is loaded, instead of accepting any chapter string.

**Verification status:** Math (Class 7/8/9) was rebuilt from published KTBS
English-medium contents. Science, Social Science, English and Kannada are still
the earlier interim lists - re-ingest them from the current-year KTBS PDFs
(`scripts/ingest_syllabus.py`, add per-grade lists) before relying on them.
Karnataka has had old and revised editions of several books; confirm which
one your schools use.

## Textbooks supersede this file

With textbooks ingested into `backend/data/textbooks/` (see
`generation_engine/README.md`), the syllabus is derived from them. With
`REQUIRE_TEXTBOOK=true`, this `syllabus.json` is **not read at all** — it is only a
fallback for (subject, grade) pairs that have no textbook yet when the flag is off.
