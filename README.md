# KRIES Question Bank Generator

An AI-powered question bank generator for the **Karnataka State Board, grades 7–9**.
It generates syllabus-aligned practice questions — MCQ, short answer, long
answer, fill in the blank, and match the following — complete with answer keys, difficulty tagging, and marks-aware answer
formatting. Teachers use it to assemble question papers; students use it for
self-study practice.

**Status:** the generation engine and the FastAPI backend work end to end, and both
automated suites pass (307 + 677 tests). The React web app covers sign-up/sign-in,
password reset, question banks, blueprint-based question papers, an admin-managed figure
library for diagram questions, answer-key verification, PDF export with an optional
student copy , per-user settings and a dark theme. 

## What problem this solves

Setting good practice questions per chapter, per grade, per mark value is slow
manual work for teachers. This tool generates a batch of them on demand from an
LLM, validates that each one is actually usable (schema-correct, non-duplicate,
answer depth matching the marks it's worth), stores it, and lets a teacher
assemble a subset into a printable question paper or a student pull a subset
into a self-check practice session with answers withheld until revealed.

## Locked project decisions

| Area | Decision |
|---|---|
| Board / Grades | Karnataka State Board, grades 7–9 |
| Subjects | Math, Science, Social Science, English(1st language), Kannada(1st language) |
| Question types | MCQ, Short answer, Long answer, Fill in the blank, Match the following |
| LLM API for generation | Groq |
| Frontend | **React + TypeScript + Vite + Tailwind web app** (built)|
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Auth | Sign-up / sign-in with JWT bearer tokens; roles Teacher, Student and Admin; password reset by emailed single-use link; papers and practice sessions are private to their owner; per-user and per-IP rate limits (see `docs/api-contract.md` and `backend/README.md`) |
| Syllabus data source | Parsed from textbook PDFs. The ingestion CLIs are built; the shipped `syllabus.json` (296 chapter names across the five subjects, scoped per grade) was transcribed by hand from textbook contents pages, not produced by the CLI |
| Diagrams | A shared figure library, managed by administrators only. Questions can carry a diagram in the paper and a possibly different one in the answer key |
| Hosting | AWS |

## Architecture 

```
generation_engine/   Module A — prompts → Groq → validated Question objects
backend/              Module B — FastAPI + PostgreSQL, REST API, PDF export
frontend/             Module C — React + Vite web app, wired to the backend (see frontend/README.md)
scripts/              Standalone CLIs: live smoke test, syllabus and textbook PDF ingestion,
                      admin and figure tools
.github/workflows/    CI — runs both test suites on every push/PR
```

They compose like this:

```
React web app (frontend/)
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

### The shared contract every module builds against

```json
{
  "id": "uuid",
  "subject": "Math | Science | Social Science | English | Kannada",
  "chapter": "string",
  "type": "MCQ | Short | Long | Fill | Match",
  "grade": 8,
  "text": "string",
  "options": ["string"],
  "answer": "string",
  "explanation": "string",
  "marks": 1,
  "difficulty": "easy | medium | hard",
  "topic": "string",
  "tags": ["string"],
  "figure_id": "uuid | null",
  "verification_status": "unverified | verified | flagged",
  "verification_note": "string | null"
}
```

Syllabus hierarchy is `Subject → Chapter → Questions`. `topic` is a free-text
tag on the question's answer key describing the sub-topic within the chapter —
it is not a separate hierarchy level.

### The most important domain rule: marks-aware answers

An answer's depth and format must match the marks it's worth, mirroring how a
real Karnataka State Board exam is evaluated:

| Marks | Expected answer format |
|---|---|
| 1 | Single word/phrase, no explanation |
| 2 | 1–2 lines with one supporting point |
| 3 | Exactly 3 distinct points or steps |
| 5 | Detailed, multi-point/step answer, structured like a full exam response |

Supported (type, marks) combinations, enforced by the engine and exposed at
`GET /generation/combinations`:

| Type | Marks | Notes |
|---|---|---|
| MCQ | 1 | 4 options, one correct |
| Short | 1, 2, 3 | formats as in the table above |
| Long | 3, 5 | 3 marks: exactly 3 points; 5 marks: at least 3 points, 40+ words |
| Fill | 1 | one or more blanks written as `___` |
| Match | 3, 5 | marks = number of pairs; Column A items and Column B items must each be distinct |

This is subject-specific — Math's 5-mark answers need step-by-step
derivations, Social Science's need labeled sections (causes/effects), Science
should reference diagrams where relevant. MCQs always get one correct option
plus a 1-line justification, regardless of marks. This rule is enforced by
`generation_engine/subject_formats.py` and re-checked server-side whenever a
question is edited (`PATCH /questions/{id}`), so a hand-edit (for example
changing the marks) can't leave an answer that no longer fits. The answer
itself is read-only.

## Strictly Karnataka State Board, from the textbook

Drop the KTBS PDFs (`science_8.pdf`, `math_7_1.pdf`, ...) in a folder and run
`python scripts/ingest_textbooks.py pdfs/ --write`. Chapters per grade come from
the textbooks, questions are written from their passages and spread over the whole
chapter, and `REQUIRE_TEXTBOOK=true` refuses anything not backed by an ingested
book. Details: `generation_engine/README.md`.

## Repo layout

```
generation_engine/   Module A — see generation_engine/README.md
backend/              Module B — see backend/README.md
frontend/             Module C — see frontend/README.md
docs/                 Full spec, API contract, DB schema, ADRs, test plan
scripts/              smoke_generate.py (hits real Groq, not mocked), ingest_syllabus.py,
                      ingest_textbooks.py, make_admin.py, upload_figure.py, check_figures.py
backend/scripts/      bulk_generate.py (+ bulk/ one-line wrappers per grade and subject),
                      seed_figures.py, seed_model_papers.py
backend/data/         syllabus.json, figures/ (diagram library + manifests), model_papers/
                      (previous papers as JSON), textbooks/ (ingested corpus, empty until you ingest)
tests/                Module A's test suite (the backend's lives in backend/tests/)
```

Start with `docs/project-context.md` for a condensed brief, or the individual
docs below for full detail:

| Doc | Contents |
|---|---|
| `docs/spec.md` | Full project specification |
| `docs/api-contract.md` | Complete REST endpoint reference (request/response shapes) |
| `docs/db-schema.md` | Complete database schema |
| `docs/prompt-library.md` | Finalized generation prompts per question type/marks |
| `docs/adr.md` | Architecture decisions and the reasoning behind each |
| `docs/test-plan.md` | Test case catalog |
| `docs/ui-wireframes.md` | Planned frontend screens and navigation flow |
| `docs/task-tracker.md` | Sprint-by-sprint task board (source of truth for what's done vs. open) |

## Getting started

### 1. Generation engine (Module A)

```bash
# from the repo root
pip install -r requirements.txt
echo "GROQ_API_KEY=your-key-here" > .env     # only needed for real generation, not for the tests
pytest                      # 307 tests, no network required — fully mocked
```

The engine's tests live in the repo-root `tests/` folder (that is what `pytest.ini` points at),
so run `pytest` from the repo root, not from inside `generation_engine/`. The default model is
`openai/gpt-oss-120b`; set `GROQ_MODEL` to change it.

Sanity-check against the **real** Groq API (not mocked) before trusting it:
```bash
python scripts/smoke_generate.py
python scripts/smoke_generate.py --subject Math --chapter "Linear Equations" --type Short --marks 3 --count 5
python scripts/smoke_generate.py --all-subjects --json
```

**Syllabus data:** `backend/data/syllabus.json` ships with a hand-transcribed, per-grade
chapter list (296 chapter names, 5 subjects) so the chapter picker isn't empty on a fresh
install — see `backend/data/README.md` for how each subject was sourced and what still needs
checking. To ingest chapter lists from textbook PDFs instead:
```bash
# Dry run first (the default) — find the real contents-page range, review output
python scripts/ingest_syllabus.py textbook.pdf --subject Science --pages 1-10

# Narrow to the real range, then write for real
python scripts/ingest_syllabus.py textbook.pdf --subject Science --pages 4-5 --write
```

### 2. Backend (Module B)

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r ../requirements.txt -r requirements.txt

# create backend/.env — for local dev the default SQLite DATABASE_URL works as-is, so
# this can be as small as:   JWT_SECRET=<any long random string>
# (GROQ_API_KEY can live here or in the repo-root .env; every setting is in app/config.py)
alembic upgrade head        # creates the 9 tables (SQLite dev databases create themselves on startup)
uvicorn app.main:app --reload
```

Interactive API docs: `http://localhost:8000/docs`. Health check: `/health`.

```bash
pytest    # 677 pass, 1 skipped (a WeasyPrint-only test, when WeasyPrint isn't installed)
          # in-memory SQLite + a stubbed Groq client — no network, no real DB needed
```

**Database:** for local development use SQLite (`DATABASE_URL=sqlite+aiosqlite:///./question_bank.db`),
no server needed. For production use any PostgreSQL, including a free
[Supabase](https://supabase.com) project. Use the **direct connection** or **session
pooler** (port `5432`), not the transaction pooler (port `6543`) — the app's `asyncpg`
driver uses prepared statements, which the transaction pooler doesn't support without
extra config this project doesn't set.

**Set `JWT_SECRET`** in any real deployment; otherwise a
random key is generated per process and everyone is signed out on every restart.

### 3. Frontend (Module C)

```bash
cd frontend
cp .env.example .env
npm install
npm run dev                 # http://localhost:5173 — Vite proxies /api to the backend on :8000
```

Pages: sign in / sign up / forgot password / reset password, Dashboard, Generate,
Question Papers (blueprint builder), Question Banks (+ detail, with PDF export and an
answer-key toggle), Settings, and — for administrators only — Figure Library. See
`frontend/README.md` for how each screen maps to the API.

> `npm run build` currently fails (type errors in leftover prototype files); `npm run dev`
> is unaffected because Vite does not type-check. See [Current status](#current-status).

### Sending password-reset emails

`POST /auth/forgot-password` emails a link that is valid for 30 minutes and works once.
With `SMTP_HOST` empty (the default) no email is sent: the link is **printed in the backend
log**, which is all you need locally. For real email set `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY` and `FRONTEND_URL` in
`backend/.env` (a Gmail app password works; details in `backend/README.md`).

## CI

`.github/workflows/tests.yml` runs both Python test suites (generation-engine and
backend, as two parallel jobs, Python 3.12) on every push and PR to `main`. The frontend is not part
of CI yet (`npm run build` and `npm run lint` are run by hand — which is how the broken build
went unnoticed). No secrets
are configured for it, deliberately — both suites are fully mocked (fake
Groq HTTP responses) or run against in-memory SQLite, so a passing local run
should mean a passing CI run and vice versa. If a test ever starts requiring
a real `GROQ_API_KEY` or `DATABASE_URL` to pass, that's a regression, not a
CI config gap to patch around.

## Known gotchas (already fixed / worth knowing about)

These came up during first-time setup and are worth flagging so nobody
re-discovers them the hard way:

- **`DATABASE_URL` needs the `+asyncpg` driver.** A bare `postgresql://...`
  URL fails at startup (`ModuleNotFoundError: psycopg2`) — both the app and
  Alembic use the async engine. Must be
  `postgresql+asyncpg://user:pass@host:5432/dbname`.
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
- **Reset links point at `FRONTEND_URL`.** It defaults to `http://localhost:5173`; if you
  deploy and leave it, users get a reset link that opens localhost. Set it to the real
  frontend origin.
- **Rate limits are per process.** Counters live in memory, so with several workers or
  instances each keeps its own counts. Move the store to Redis before scaling out.
- **PowerShell isn't bash.** `createdb`/`psql` are PostgreSQL client binaries,
  not shell builtins — need PostgreSQL's `bin` folder on `PATH`, or skip them
  entirely by using a hosted Postgres (Supabase). Inline env vars
  (`VAR=value command`) don't work in PowerShell — use `$env:VAR = "value"`
  on its own line first. `curl` is aliased to `Invoke-WebRequest`, which
  takes different flags than real curl — use `Invoke-RestMethod` for JSON
  APIs, or call `curl.exe` explicitly for the real thing.

## Accounts and settings

- **Sign-up / sign-in** — JWT bearer tokens (`POST /auth/signup`, `/auth/login`, `GET /auth/me`).
  Roles are `Teacher` or `Student`; `Admin` can never be self-assigned. Wrong passwords
  are rate-limited per (IP, email) and lock that pair out for 15 minutes.
- **Forgot / reset password** — `POST /auth/forgot-password` always answers the same way, whether or
  not the email has an account, and sends the email after responding, so it can't be used to find
  out who is registered. `POST /auth/reset-password` takes the emailed token plus a new password. The
  token is bound to the current password hash, so it is single-use and needs no extra table.
- **Settings** — `PATCH /auth/me` saves the profile (name, role) and preferences (theme, in-app
  notifications, default question count / difficulty / type / marks) to the `users` table
  (`users.preferences`, migration `0005`). They follow the user across devices. The **email can't be
  changed**: the endpoint answers 403. Choosing a theme previews it immediately and it is applied
  app-wide (Light, Dark, or System), before first paint.
- **Students and generation** — students can generate question banks and build papers, database
  first: stored questions are always used before the model is asked for anything, only the shortfall
  is generated, students cannot force fresh generation (`refresh` is ignored), and the new questions
  they may create are capped per request and per day (`STUDENT_MAX_NEW_QUESTIONS_PER_REQUEST` = 10,
  `STUDENT_MAX_NEW_QUESTIONS_PER_DAY` = 30; teachers are not capped). A paper that would not fit is
  refused up front, before any API call. The AI answer-key check ("Verify answers") stays teacher-only.
  Details in `backend/README.md`.
- **Administrators** — the `Admin` role can upload, edit and delete figures in the shared figure
  library; everyone signed in can use it. It is granted on the server
  (`python scripts/make_admin.py someone@school.in`, `--demote` to undo, `--list` to see who has it).
  Sign-up only offers Teacher and Student and `PATCH /auth/me` refuses `Admin`.
- **Ownership** — papers and practice sessions are private to their owner; the question pool is
  shared (anyone signed in can reuse stored questions, only the creator can edit or discard one).

## Question Papers (blueprint-based papers)

The **Question Papers** page builds a board-style paper from a *blueprint*
instead of a hand-picked list:

- **Chapters + weightage** — pick any number of chapters (up to 12) and give each a
  share of the paper's marks; the shares must add up to 100%.
- **Sections** — each section has a question type, marks per question and a total
  (e.g. "Section B: Short answer, 2 marks each, 10 marks" = 5 questions). Difficulty is
  per section, and `mixed` cycles easy / medium / hard.

```
POST /api/v1/papers/blueprint/preview   how the marks split across chapters (no LLM, no writes)
POST /api/v1/papers/blueprint           build and save the paper (returns a normal PaperOut)
POST /api/v1/papers/blueprint/jobs      the same build in the background; poll GET .../jobs/{id}
                                        for done/total questions (drives the page's progress bar)
```

How it works (`backend/app/services/blueprint.py`):

1. **Allocation** is plain arithmetic. Each chapter's target is `weightage% x total
   marks`; questions are handed out biggest-marks first, each to the chapter furthest
   below its target. It is deterministic, which is what lets the page preview it live.
   Questions are whole units, so a chapter can miss its target by a mark or two (two
   5-mark questions cannot cover four chapters at 25% each) — the preview shows the
   achieved figure next to the target.
2. **Fetching** goes through the same service as `POST /generate`: stored questions are
   reused and only the shortfall is generated. Tick *Always generate new questions*
   (`refresh`) to skip the stored ones; otherwise repeating a blueprint returns the same
   paper.
3. **All-or-nothing.** The request is one transaction; if any generation call fails
   (502/422) no paper and no new questions are stored.

Sections are stored on `paper_questions.section` (migration `0004`; `ensure_schema`
adds the column on startup for databases created without Alembic), so the bank page and
all three PDF renderers show "Section A ... 10 marks" headings. Papers built by hand
have no sections and render exactly as before. A blueprint paper may have at most 100
questions, and `POST /papers/blueprint` shares the per-user `RATE_LIMIT_GENERATE` budget
with `/generate` because it can make many LLM calls.

## Diagrams, answer verification and bulk data

- **Figure library.** Administrators upload diagrams (re-encoded on upload, never stored as
  received) and tag each with subject, chapter, topic, caption and labelled parts. Generating a
  bank or blueprint paper can mix in diagram-based questions (`mix_figures`), or write questions
  about chosen figures (`use_figures` / `figure_ids`): the model is given the figure's *metadata*
  as text, never the image. A question can carry one diagram in the paper and another in the
  answer key. The repo ships 49 Science diagrams with a manifest, plus grade 7, 8 and 9 folders
  under `backend/data/figures/`. `scripts/check_figures.py` reports figures that can't be used
  (retired chapter name, or image file missing from disk). Details: `backend/README.md`.
- **Answer-key verification.** The model that writes a question also writes its answer, so
  checking is a separate, on-demand step (**Verify answers**, `POST /questions/verify`): exact rule
  checks first, then an independent AI pass. Each question ends up `verified`, `unverified` or
  `flagged`; flagged questions are never served from the cache or used in practice sessions.
- **PDF export.** `POST /export/{id}` takes `include_answer_key` (default `true`); the question
  bank page offers a toggle, so a student copy without answers is one click.
- **Bulk generation and model papers.** `backend/scripts/bulk_generate.py` (and the one-line
  wrappers in `backend/scripts/bulk/`, one per grade and subject) fills the bank through the normal
  `POST /generate` path. `backend/scripts/seed_model_papers.py` loads previous papers from
  `backend/data/model_papers/` (tagged `previous-paper`; 4-mark questions are skipped unless you
  pass `--four-mark-as`).

## Current status

**Built and covered by tests** (no network or database needed to run them):

- ✅ Generation engine — five question types, prompts, Groq client with retry/backoff, validation,
  marks-aware checks, textbook grounding, answer-key rule checks and AI verification (307 tests)
- ✅ Backend — every endpoint in `docs/api-contract.md`, plus papers list, blueprint papers and
  background jobs, auth, password reset, profile/preferences, figure library and answer verification
  (677 pass, 1 skipped when WeasyPrint isn't installed)
- ✅ PDF export — WeasyPrint, ReportLab and fpdf renderers; Kannada papers export correctly via
  WeasyPrint or fpdf (fonts bundled in `backend/assets/fonts`); the answer key is optional
- ✅ Migrations `0001`–`0009`, plus `ensure_schema` for SQLite databases created by an older version
- ✅ CI — both Python suites, in fresh environments, with no secrets configured
- ✅ Frontend features — sign-in/up, forgot/reset password, dashboard, generate (all five types, verify
  answers, diagram questions), blueprint question papers with a progress bar, question banks with PDF
  export, settings, light/dark/system theme, and an admin-only Figure Library. `npm run lint` reports
  0 errors (7 warnings). There are no automated UI tests.

**Broken right now — the frontend build.** `npm run build` fails with 42 type errors, all in seven
leftover prototype files that nothing in the live app imports:

```
frontend/src/pages/AnalyticsPage.tsx
frontend/src/data/mockData.ts   frontend/src/data/syllabus.ts   frontend/src/data/analytics.ts
frontend/src/lib/analytics.ts   frontend/src/lib/generator.ts   frontend/src/lib/storage.ts
```

They refer to things that no longer exist (Bloom's level, bank descriptions, API helpers that were
removed) and to `recharts`, which is not in `package.json`. The Analytics page is not routed. Deleting
the seven files is the fix: with them removed the type-check and `vite build` pass. `npm run dev`
still works because Vite does not type-check.

**Verified by hand against live services** (a real Groq key and a Supabase Postgres, in an earlier pass):
`POST /generate` writing real rows, paper creation, PDF export (including the character-encoding fix),
syllabus seeding on an empty database, and the syllabus PDF-ingestion CLI. The auth, password-reset,
settings and blueprint features were tested with the automated suite only, and this README does not
record a live check of what came later (figure library, answer verification, Fill and Match types,
background paper jobs).

**Still open** (`docs/task-tracker.md` has the full board, and may lag behind this list):

- ⬜ Fix the frontend build (above), then add it to CI
- ⬜ Android build — only the web app exists; React Native was the original plan
- ⬜ Frontend has no automated tests
- ⬜ Syllabus accuracy: `backend/data/syllabus.json` was transcribed by hand. Math comes from published
  KTBS contents (third-party mirrors); Science, Social Science, English and Kannada come from photos of
  contents pages with the grade assigned from content or upload order, and are marked "confirm" in the
  file. Nothing has been run through the PDF ingestion CLIs, and `backend/data/textbooks/` is empty, so
  textbook-grounded generation has not been used against real books
- ⬜ Practice sessions exist in the API only; the web app has no practice screen
- ⬜ The backend suite has never been run against a live PostgreSQL database (only in-memory SQLite,
  which masks Postgres-only behaviour such as native enums, `jsonb` and `text[]`). CI runs the same suite
- ⬜ Rate limiting is in-memory (single process); needs a shared store before running several instances
- ⬜ Figure images live on local disk (`FIGURE_DIR`): on a host without a persistent volume they vanish
  on redeploy while the database rows survive (`scripts/check_figures.py` reports this). Needs object storage
- ⬜ Password-reset email has been tested with a stubbed sender, not against a real SMTP server
- ⬜ Production hosting target (AWS vs. Render) not decided; the frontend is not deployed
- ⬜ Export files are never cleaned up — no retention policy yet
- ⬜ Generation quality: the duplicate-similarity threshold (0.90) and word-count bounds are first
  estimates. Answer keys get rule checks and a second AI opinion on demand, but no human fact-check per
  subject, and editing a question's text or options does not re-run verification

**Housekeeping**

- `generation_engine/test_prompts.py`, `test_schemas.py` and `test_validation.py` are stale copies of
  older tests. Pytest and CI never collect them (`testpaths = tests`), and 27 of their 34 tests fail if
  you run them directly. Delete them or bring them up to date
- `generation_engine/Unconfirmed 568007.crdownload` is a stray browser download; delete it
- There is no `.env.example` for the repo root or `backend/` (only `frontend/.env.example`); adding
  them would make first-time setup easier. Every backend setting is defined in `backend/app/config.py`
  and every engine setting in `generation_engine/config.py`
- `docs/api-contract.md`, `docs/db-schema.md` and `docs/task-tracker.md` still lag the code in places

## Tech stack summary

- **Generation:** Python, Groq API (default model `openai/gpt-oss-120b`, set with `GROQ_MODEL`), Pydantic schemas
- **Syllabus and textbook ingestion:** `pypdf` (text extraction) + regex line-parsing,
  `scripts/ingest_syllabus.py`, `scripts/ingest_textbooks.py`
- **Backend:** FastAPI, SQLAlchemy (async; `asyncpg` for PostgreSQL, `aiosqlite` for local dev), Alembic,
  PyJWT, scrypt password hashing, Pillow (figure uploads)
- **PDF export:** WeasyPrint (preferred), fpdf2 + HarfBuzz (pure pip, Kannada-capable), or ReportLab
  (no system dependencies, Latin scripts only)
- **Frontend:** React 19, TypeScript, Vite 8, Tailwind CSS 4, React Router 7, lucide-react
- **Testing:** pytest, in-memory SQLite + stubbed Groq client (no network/DB required); a separate live
  smoke-test script for real-API verification
- **CI:** GitHub Actions, two jobs (generation-engine, backend), on every push/PR to `main` — no secrets required
