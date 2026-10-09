# `backend/data/`

| Path | What it is |
|---|---|
| `syllabus.json` | The chapter allow-list for grades 7–9, scoped per grade (below) |
| `figures/` | The diagram library: images plus manifests for loading them |
| `model_papers/` | Previous / model question papers as JSON, loaded by `scripts/seed_model_papers.py` |
| `textbooks/` | Ingested KTBS textbook corpus. Empty until you run `scripts/ingest_textbooks.py` |

# `syllabus.json`

Hand-transcribed chapter list for grades 7–9 (Karnataka State Board), scoped **per grade** for all five
subjects: 296 chapter names, 303 grade-chapter entries (a name shared by two grades counts once in the first
number and twice in the second).

| Subject | Grade 7 | Grade 8 | Grade 9 |
|---|---|---|---|
| Math | 15 | 16 | 15 |
| Science | 12 | 13 | 12 |
| Social Science | 27 | 30 | 33 |
| English | 19 | 22 | 24 |
| Kannada | 21 | 22 | 22 |

It exists so the frontend's subject/chapter picker has something to show on a fresh install: without it,
`GET /subjects/{subject}/chapters` returns `[]` until someone generates a question for a chapter first.
It was **not** produced by the PDF-parsing pipeline (`scripts/ingest_syllabus.py`), which has not yet been run
against real textbook files. Loaded via the `SYLLABUS_JSON_PATH` setting in `backend/.env`; the shape is defined
by `generation_engine/syllabus.py`'s `SyllabusIndex.from_json`.

## How each subject was sourced, and what is still unconfirmed

The same notes are recorded in the file's `_meta.verification` block.

- **Math** — Class 7/8/9 lists taken from published KTBS English-medium contents (third-party mirrors).
  Re-check against the current-year KTBS PDFs.
- **Science** — transcribed from photos of the KTBS contents pages (Class 7 and 8 are the revised books;
  Class 9 is printed in two volumes with interleaved chapter numbers, listed here in chapter-number order).
  The photos carried no class label, so grades were assigned from the chapter content. Confirm.
- **Social Science** — transcribed from photos (both volumes per grade; History, Civics, Political Science,
  Sociology, Geography, Economics and Business Studies in one list, in textbook order). Grades were assigned by
  **upload order and not confirmed**; the content does not run ancient → medieval → modern across 7 → 8 → 9,
  so verify this one first.
- **English** — prose, poetry and supplementary-reading lessons transcribed from photos, in unit order. Only
  items printed in the contents are listed (including Study Skills, Table of Contents, List of Phonetic Symbols
  in English, and Letter Writing & Determiners). Grades assigned by upload order and lesson level; the language
  level (first / second / third) was not stated. Confirm.
- **Kannada** — first-language lessons in Kannada script: Gadya (prose), Padya (poetry) and the supplementary
  ಪೂರಕ / ಪಠ್ಯಪೂರಕ lessons, keeping the "(ಗದ್ಯ)" / "(ಪದ್ಯ)" suffix the book prints, both volumes per grade. Remove the
  supplementary ones from a grade if your question papers never draw from them. Grades assigned by upload order
  and lesson level; transcribed from photos, so spot-check spellings. Matching ignores ZWNJ/ZWJ but not other
  differences. Not included: the *Tili Kannada* (2nd language) and *Nudi Kannada* (3rd language) textbooks.

Karnataka has had old and revised editions of several books; confirm which one your schools use.

## Strict Karnataka State Board enforcement

The engine treats this file as the allow-list. A request is rejected (HTTP 400) unless its chapter is in the
requested **grade's** list for that subject, and the prompt tells the model to stay inside that chapter of the
KTBS textbook.

- `grades` -> enforced per grade. All five subjects now have it. A subject without a `grades` entry can't be
  grade-checked: any listed chapter is accepted for any grade.
- `topics` (optional, `{chapter: [sub-topics]}`) -> injected into the prompt to bound each chapter's scope. No
  subject uses it at the moment.
- `_meta` -> provenance; ignored by the loader.
- `REQUIRE_SYLLABUS=true` (engine/backend env) refuses generation when no syllabus is loaded, instead of
  accepting any chapter string.

## Textbooks supersede this file

With textbooks ingested into `backend/data/textbooks/` (see `generation_engine/README.md`), the syllabus is
derived from them. With `REQUIRE_TEXTBOOK=true`, this `syllabus.json` is **not read at all** — it is only a
fallback for (subject, grade) pairs that have no textbook yet when the flag is off.

# `figures/`

The diagram library that administrators manage through the web app's Figure Library page. Everything here is
loaded through the same `POST /figures` endpoint (see the Figures section of `backend/README.md`).

- **`*.png` + `manifest.json` (top level)** — 49 Science diagrams. Load with
  `python scripts/upload_figure.py --manifest backend/data/figures/manifest.json --admin <email>`.
- **`grade7/`, `grade8/`, `grade9/`** — per-grade folders, each with its own `manifest.json`. Load with
  `python backend/scripts/seed_figures.py --token <ADMIN_JWT> --grades 7 8 9` (the default is grades 7 and 8).
  Manifests list 53 figures (grade 7), 65 (grade 8) and 68 (grade 9). The grade 9 folder also holds 10 images with no
  manifest entry (parenchyma cells, collenchyma, phloem, paramoecium, permanent-tissue flowchart, neuron, prokaryotic
  cell, atom energy levels, muscle fibre types, amoeba), which `seed_figures.py` will not load, and a `_duplicates/`
  subfolder.
- **`chapter_map.json`** — old chapter name -> current KTBS chapter name, for figures tagged before the syllabus was
  replaced. Used by `python scripts/check_figures.py --apply`.
- **`_unused/`** — images set aside (currently 27, under `grade8/`); nothing reads this folder.

A figure is only picked for diagram questions when its subject and chapter exactly match a chapter in the current
syllabus; `scripts/check_figures.py` reports the ones that don't.

# `model_papers/`

`sa2_grade7_en.json`, `sa2_grade8_en.json` and `sa2_grade9_en.json`: previous papers, each with `paper`, `grade` and
`questions`. `python backend/scripts/seed_model_papers.py` stores them as questions tagged `previous-paper`. Questions
with no matching chapter and 4-mark questions are skipped and reported (see `backend/README.md`).
