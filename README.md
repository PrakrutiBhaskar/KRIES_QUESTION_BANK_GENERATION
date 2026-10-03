# KRIES Question Bank Generator

An AI-powered question bank generator for the **Karnataka State Board, grades 7–9**.
It generates syllabus-aligned practice questions — MCQ, short answer, and long
answer — complete with answer keys, difficulty tagging, and marks-aware answer
formatting. Teachers use it to assemble question papers; students use it for
self-study practice. Built by a 3-person team, one module per person.

**Status:** all three modules work end to end — generation engine, FastAPI backend,
and a React web app with sign-up/sign-in, password reset, question banks,
blueprint-based question papers, PDF export (including Kannada), per-user settings
and a dark theme. See [Current status](#current-status) for what is verified and
what is still open.

## What problem this solves

Setting good practice questions per chapter, per grade, per mark value is slow
manual work for teachers. This tool generates a batch of them on demand from an
LLM, validates that each one is actually usable (schema-correct, non-duplicate,
answer depth matching the marks it's worth), stores it, and lets a teacher
assemble a subset into a printable question paper — or a student pull a subset
into a self-check practice session with answers withheld until revealed.

## Locked project decisions

| Area | Decision |
|---|---|
| Board / Grades | Karnataka State Board, grades 7–9 |
| Subjects | Math, Science, Social Science, English, Kannada |
| Question types | MCQ, Short answer, Long answer |
| LLM API for generation | Groq |
| Frontend | **React + TypeScript + Vite + Tailwind web app** (built). The original plan was React Native for Web + Android; the web app shipped first and an Android build is still open |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Auth | Sign-up / sign-in with JWT bearer tokens; password reset by emailed single-use link; papers and practice sessions are private to their owner; per-user and per-IP rate limits (see `docs/api-contract.md` and `backend/README.md`) |
| Syllabus data source | Parsed from textbook PDFs. The ingestion CLI is built; the shipped chapter list (194 chapters) is still hand-curated |
| Hosting | AWS preferred, Render as fallback |

## Architecture — three modules, one per team member

```
generation_engine/   Module A — prompts → Groq → validated Question objects
backend/              Module B — FastAPI + PostgreSQL, REST API, PDF export
frontend/             Module C — React + Vite web app, wired to the backend (see frontend/README.md)
scripts/              Standalone CLIs: live smoke test, syllabus PDF ingestion
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
it is *not* a separate hierarchy level.

### The most important domain rule: marks-aware answers

An answer's depth and format must match the marks it's worth, mirroring how a
real Karnataka State Board exam is evaluated:

| Marks | Expected answer format |
|---|---|
| 1 | Single word/phrase, no explanation |
| 2 | 1–2 lines with one supporting point |
| 3 | Exactly 3 distinct points or steps |
| 5 | Detailed, multi-point/step answer, structured like a full exam response |

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
                      ingest_textbooks.py, make_admin.py, upload_figure.py
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
cd generation_engine
pip install -r requirements.txt
cp .env.example .env        # add your GROQ_API_KEY
pytest                      # 210 tests, no network required — fully mocked
```

Sanity-check against the **real** Groq API (not mocked) before trusting it:
```bash
python scripts/smoke_generate.py
python scripts/smoke_generate.py --subject Math --chapter "Linear Equations" --type Short --marks 3 --count 5
python scripts/smoke_generate.py --all-subjects --json
```

**Syllabus data:** `backend/data/syllabus.json` ships with a manually-curated
interim chapter list (194 chapters, 5 subjects) so the chapter picker isn't
empty on a fresh install — see `backend/data/README.md`. To ingest real
chapter lists from actual textbook PDFs instead:
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

cp .env.example .env        # local dev: the default SQLite DATABASE_URL works as-is
alembic upgrade head        # creates the 8 tables (SQLite dev databases create themselves on startup)
uvicorn app.main:app --reload
```

Interactive API docs: `http://localhost:8000/docs`. Health check: `/health`.

```bash
pytest    # 592 tests, in-memory SQLite + a stubbed Groq client — no network, no real DB needed
```

**Database:** for local development use SQLite (`DATABASE_URL=sqlite+aiosqlite:///./question_bank.db`),
no server needed. For production use any PostgreSQL, including a free
[Supabase](https://supabase.com) project. Use the **direct connection** or **session
pooler** (port `5432`), not the transaction pooler (port `6543`) — the app's `asyncpg`
driver uses prepared statements, which the transaction pooler doesn't support without
extra config this project doesn't set.

**Set `JWT_SECRET`** (see `backend/.env.example`) in any real deployment; otherwise a
random key is generated per process and everyone is signed out on every restart.

### 3. Frontend (Module C)

```bash
cd frontend
cp .env.example .env
npm install
npm run dev                 # http://localhost:5173 — Vite proxies /api to the backend on :8000
```

Pages: sign in / sign up / forgot password / reset password, Dashboard, Generate,
Question Papers (blueprint builder), Question Banks (+ detail), Settings. See
`frontend/README.md` for how each screen maps to the API.

### Sending password-reset emails

`POST /auth/forgot-password` emails a link that is valid for 30 minutes and works once.
With `SMTP_HOST` empty (the default) no email is sent: the link is **printed in the backend
log**, which is all you need locally. For real email set `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY` and `FRONTEND_URL` in
`backend/.env` (a Gmail app password works; details in `backend/README.md`).

## CI

`.github/workflows/tests.yml` runs both Python test suites (generation-engine and
backend, as two parallel jobs) on every push and PR to `main`. The frontend is not part
of CI yet (`npm run build` and `npm run lint` are run by hand). No secrets
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

## Current status

**Built and covered by tests** (no network or database needed to run them):

- ✅ Generation engine — prompts, Groq client with retry/backoff, validation, marks-aware checks (210 tests)
- ✅ Backend — every endpoint in `docs/api-contract.md`, plus papers list, blueprint papers, auth,
  password reset and profile/preferences (592 tests)
- ✅ Frontend — sign-in/up, forgot/reset password, dashboard, generate, blueprint question papers,
  question banks, settings, light/dark/system theme (builds with `npm run build`; no automated UI tests)
- ✅ PDF export — WeasyPrint, ReportLab and fpdf renderers; Kannada papers export correctly via
  WeasyPrint or fpdf (fonts bundled in `backend/assets/fonts`)
- ✅ Migrations `0001`–`0008`, plus `ensure_schema` for SQLite databases created by an older version
- ✅ CI — both Python suites, in fresh environments, with no secrets configured

**Verified by hand against live services** (a real Groq key and a Supabase Postgres, in an earlier pass):
`POST /generate` writing real rows, paper creation, PDF export (including the character-encoding fix),
syllabus seeding on an empty database, and the syllabus PDF-ingestion CLI. The auth, password-reset,
settings and blueprint features were tested with the automated suite only.

**Still open** (`docs/task-tracker.md` has the full board, and may lag behind this list):

- ⬜ Android build — only the web app exists; React Native was the original plan
- ⬜ Frontend has no automated tests and is not in CI
- ⬜ `backend/data/syllabus.json` is still hand-curated (194 chapters), not parsed from real textbook
  PDFs — the ingestion pipeline (`scripts/ingest_syllabus.py`) is built and tested, just not yet
  pointed at actual textbook files
- ⬜ Answer key is *always* included in the exported PDF — there is no way to request a student-facing
  version without answers (the renderer supports it; the API doesn't expose it yet)
- ⬜ The backend suite has never been run against a live PostgreSQL database (only in-memory SQLite,
  which masks Postgres-only behaviour such as native enums, `jsonb` and `text[]`). CI runs the same suite
- ⬜ Rate limiting is in-memory (single process); needs a shared store before running several instances
- ⬜ Password-reset email has been tested with a stubbed sender, not against a real SMTP server
- ⬜ Production hosting target (AWS vs. Render) not decided; the frontend is not deployed
- ⬜ Export files are never cleaned up — no retention policy yet
- ⬜ Chapter weighting and generation quality: duplicate-similarity threshold (0.90) and word-count
  bounds are first estimates, and answers have not been fact-checked per subject

## Tech stack summary

- **Generation:** Python, Groq API (`openai/gpt-oss-120b`), Pydantic schemas
- **Syllabus ingestion:** `pypdf` (text extraction) + regex line-parsing,
  `scripts/ingest_syllabus.py`
- **Backend:** FastAPI, SQLAlchemy (async; `asyncpg` for PostgreSQL, `aiosqlite` for local dev), Alembic,
  PyJWT, scrypt password hashing
- **PDF export:** WeasyPrint (preferred), fpdf2 + HarfBuzz (pure pip, Kannada-capable), or ReportLab
  (no system dependencies, Latin scripts only)
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS 4, React Router, lucide-react
- **Testing:** pytest, in-memory SQLite + stubbed Groq client (no network/DB required); a separate live
  smoke-test script for real-API verification
- **CI:** GitHub Actions, two jobs (generation-engine, backend), on every push/PR to `main` — no secrets required
