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
