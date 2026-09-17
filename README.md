# KRIES Question Bank Generator

An AI-powered question bank generator for the **Karnataka State Board, grades 7–9**.
It generates syllabus-aligned practice questions — MCQ, short answer, and long
answer — complete with answer keys, difficulty tagging, and marks-aware answer
formatting. Teachers use it to assemble question papers; students use it for
self-study practice. Built by a 3-person team, one module per person.

## What problem this solves

Setting good practice questions per chapter, per grade, per mark value is slow
manual work for teachers. This tool generates a batch of them on demand from an
LLM, validates that each one is actually usable (schema-correct, non-duplicate,
answer depth matching the marks it's worth), stores it, and lets a teacher
assemble a subset into a printable question paper — or a student pull a subset
into a self-check practice session with answers withheld until revealed.

## Locked project decisions

| Area                   | Decision                                                                  |
| ---------------------- | ------------------------------------------------------------------------- |
| Board / Grades         | Karnataka State Board, grades 7–9                                         |
| Subjects               | Math, Science, Social Science, English, Kannada                           |
| Question types         | MCQ, Short answer, Long answer                                            |
| LLM API for generation | Groq                                                                      |
| Frontend               | React Native — single codebase for Web + Android                          |
| Backend                | Python, FastAPI                                                           |
| Database               | PostgreSQL                                                                |
| Auth                   | Not in MVP — deferred; schema has nullable `user_id` columns ready for it |
| Syllabus data source   | Parsed from textbook PDFs (not yet built)                                 |
| Hosting                | AWS preferred, Render as fallback                                         |

## Architecture — three modules, one per team member

```
generation_engine/   Module A — prompts → Groq → validated Question objects
backend/              Module B — FastAPI + PostgreSQL, REST API, PDF export
frontend/             Module C — React Native (web + Android) — not yet built
```

They compose like this:

```
React Native app
      │  REST (see docs/api-contract.md)
      ▼
FastAPI backend (backend/)
      │  imports directly, in-process
      ▼
Generation Engine (generation_engine/)
      │  HTTPS
      ▼
Groq API
```

The backend calls the generation engine as a Python import, not over HTTP —
there's no separate "Module A service" to deploy. The generation engine itself
has no storage and no HTTP layer; everything gets persisted by the backend
after the engine returns a validated batch.

### The shared contract every module builds against

```json
{
  "id": "uuid",
  "subject": "Math | Science | Social Science | English | Kannada",
  "chapter": "string",
  "type": "MCQ | Short | Long",
  "grade": 8,
  "text": "string",
  "options": ["string"],
  "answer": "string",
  "explanation": "string",
  "marks": 1,
  "difficulty": "easy | medium | hard",
  "topic": "string",
  "tags": ["string"]
}
```

Syllabus hierarchy is `Subject → Chapter → Questions`. `topic` is a free-text
tag on the question's answer key describing the sub-topic within the chapter —
it is _not_ a separate hierarchy level.

### The most important domain rule: marks-aware answers

An answer's depth and format must match the marks it's worth, mirroring how a
real Karnataka State Board exam is evaluated:

| Marks | Expected answer format                                                  |
| ----- | ----------------------------------------------------------------------- |
| 1     | Single word/phrase, no explanation                                      |
| 2     | 1–2 lines with one supporting point                                     |
| 3     | Exactly 3 distinct points or steps                                      |
| 5     | Detailed, multi-point/step answer, structured like a full exam response |

This is subject-specific — Math's 5-mark answers need step-by-step
derivations, Social Science's need labeled sections (causes/effects), Science
should reference diagrams where relevant. MCQs always get one correct option
plus a 1-line justification, regardless of marks. This rule is enforced by
`generation_engine/subject_formats.py` and re-checked server-side whenever a
question is edited (`PATCH /questions/{id}`), so a hand-edit can't drop a
3-mark answer down to one line.

## Repo layout

```
generation_engine/   Module A — see generation_engine/README.md
backend/              Module B — see backend/README.md
docs/                 Full spec, API contract, DB schema, ADRs, test plan
scripts/              Live smoke-test script (hits real Groq, not mocked)
```

Start with `docs/project-context.md` for a condensed brief, or the individual
docs below for full detail:

| Doc                      | Contents                                                               |
| ------------------------ | ---------------------------------------------------------------------- |
| `docs/spec.md`           | Full project specification                                             |
| `docs/api-contract.md`   | Complete REST endpoint reference (request/response shapes)             |
| `docs/db-schema.md`      | Complete database schema                                               |
| `docs/prompt-library.md` | Finalized generation prompts per question type/marks                   |
| `docs/adr.md`            | Architecture decisions and the reasoning behind each                   |
| `docs/test-plan.md`      | Test case catalog                                                      |
| `docs/ui-wireframes.md`  | Planned frontend screens and navigation flow                           |
| `docs/task-tracker.md`   | Sprint-by-sprint task board (source of truth for what's done vs. open) |

## Getting started

### 1. Generation engine (Module A)

```bash
cd generation_engine
pip install -r requirements.txt
cp .env.example .env        # add your GROQ_API_KEY
pytest                      # 100+ tests, no network required — fully mocked
```

Sanity-check against the **real** Groq API (not mocked) before trusting it:

```bash
python scripts/smoke_generate.py
python scripts/smoke_generate.py --subject Math --chapter "Linear Equations" --type Short --marks 3 --count 5
python scripts/smoke_generate.py --all-subjects --json
```

### 2. Backend (Module B)

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r ../requirements.txt -r requirements.txt

cp .env.example .env        # set DATABASE_URL — see gotchas below
alembic upgrade head        # creates the 7 tables
uvicorn app.main:app --reload
```

Interactive API docs: `http://localhost:8000/docs`. Health check: `/health`.

```bash
pytest    # 137 tests, in-memory SQLite + a stubbed Groq client — no network, no real DB needed
```

**Database:** any PostgreSQL works, including a free [Supabase](https://supabase.com)
project — no local Postgres install required. Use the **direct connection**
or **session pooler** (port `5432`), not the transaction pooler (port
`6543`) — the app's `asyncpg` driver uses prepared statements, which the
transaction pooler doesn't support without extra config this project doesn't
set.

### 3. Frontend (Module C)

Not built yet. See `docs/ui-wireframes.md` for the planned screens and
`docs/api-contract.md` for what the backend already exposes.

## Known gotchas (already fixed / worth knowing about)

These came up during first-time setup and are worth flagging so nobody
re-discovers them the hard way:

- **`DATABASE_URL` needs the `+asyncpg` driver.** A bare `postgresql://...`
  URL fails at startup (`ModuleNotFoundError: psycopg2`) — both the app and
  Alembic use the async engine. Must be
  `postgresql+asyncpg://user:pass@host:5432/dbname`. The repo-root
  `.env.example` (for Module A) has a bare `postgresql://` URL as a
  placeholder — don't copy that one for `backend/.env`'s `DATABASE_URL`.
- **`CORS_ORIGINS=*` in `.env` used to crash settings load.** Fixed in
  `backend/app/config.py` by annotating the field with pydantic-settings'
  `NoDecode` — otherwise pydantic-settings tries to JSON-decode any
  list-typed env value before the comma-split validator runs, and `*` isn't
  valid JSON.
- **PDF export used to silently corrupt special characters.** Groq's output
  routinely contains non-breaking hyphens and subscript/superscript digits
  (`CO₂`, `O₂`, `light‑dependent`). Base-14 PDF fonts — and some system TTFs,
  depending on what's installed on the host — have no glyph for these, and
  ReportLab drops or box-renders them silently rather than erroring. Fixed in
  `backend/app/services/export/renderer.py` by normalizing to plain ASCII
  before layout, so it's correct regardless of which font ends up registered
  on a given machine.
- **PowerShell isn't bash.** `createdb`/`psql` are PostgreSQL client binaries,
  not shell builtins — need PostgreSQL's `bin` folder on `PATH`, or skip them
  entirely by using a hosted Postgres (Supabase). Inline env vars
  (`VAR=value command`) don't work in PowerShell — use `$env:VAR = "value"`
  on its own line first. `curl` is aliased to `Invoke-WebRequest`, which
  takes different flags than real curl — use `Invoke-RestMethod` for JSON
  APIs, or call `curl.exe` explicitly for the real thing.

## Current verified status

As of the last setup pass, confirmed working end-to-end against a live Groq
key and a live Supabase Postgres instance (not mocks):

- ✅ Migrations apply cleanly (`alembic upgrade head`) — all 7 tables created
- ✅ Backend test suite passes (137 tests) against in-memory SQLite + stubbed Groq
- ✅ Live generation via `scripts/smoke_generate.py` — real Groq output, schema-valid
- ✅ Full request cycle proven with real data: `POST /generate` → rows land in
  Supabase's `subjects`/`chapters`/`questions` tables
- ✅ Paper creation (`POST /papers`) — `total_marks` correctly server-computed
- ✅ PDF export (`POST /export/{paper_id}`) — verified visually, including the
  character-encoding fix above

Still open (see `docs/task-tracker.md` for the full board):

- ⬜ Frontend (React Native) — not started
- ⬜ Syllabus PDF-parsing pipeline — chapters are currently created on first
  use from free-text input rather than validated against a fixed list
- ⬜ WeasyPrint not installed on the current dev machine — PDF export is
  running on the ReportLab fallback, which cannot render Kannada script at
  all (refuses with a 503 rather than emitting blank boxes). Needed before
  Kannada papers can be exported.
- ⬜ Answer key is currently _always_ included in the exported PDF, with no
  way to request a student-facing version without answers — worth deciding
  before the frontend's export flow assumes one or the other
- ⬜ Backend test suite has never actually been run against a live PostgreSQL
  database (only in-memory SQLite) — worth doing once before considering the
  DB layer fully proven, since SQLite masks Postgres-only behavior (native
  enums, `jsonb`, `text[]`)
- ⬜ Production hosting target (AWS vs. Render) not yet decided
- ⬜ Export files are never cleaned up — no retention policy yet

## Tech stack summary

- **Generation:** Python, Groq API (`openai/gpt-oss-120b`), Pydantic schemas
- **Backend:** FastAPI, SQLAlchemy (async, `asyncpg`), Alembic, PostgreSQL
- **PDF export:** WeasyPrint (preferred, Unicode/Kannada-capable) or ReportLab
  (no system dependencies, Latin scripts only)
- **Frontend (planned):** React Native, single codebase for Web + Android
- **Testing:** pytest, in-memory SQLite + stubbed Groq client for the backend
  suite (no network/DB required to run it); a separate live smoke-test script
  for real-API verification
