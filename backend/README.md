# Backend — Module B

FastAPI + PostgreSQL service for the Question Bank Generator. Implements the
endpoints in [`docs/api-contract.md`](../docs/api-contract.md) against the schema in
[`docs/db-schema.md`](../docs/db-schema.md), adds sign-up/sign-in, password reset,
user settings and blueprint-based papers, and calls Module A (`generation_engine/`)
for generation.

## Quick start

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r ../requirements.txt -r requirements.txt

cp .env.example .env          # local dev: the default SQLite DATABASE_URL works as-is
                              # GROQ_API_KEY goes in the repo-root .env (or backend/.env)
alembic upgrade head          # PostgreSQL only; SQLite creates its tables on startup

uvicorn app.main:app --reload
```

Interactive docs at <http://localhost:8000/docs>, health check at `/health`.

> **`DATABASE_URL` needs the `+asyncpg` driver for PostgreSQL** —
> `postgresql+asyncpg://user:pass@host:5432/question_bank_db`. A bare
> `postgresql://` URL fails at startup, because both the app and Alembic use
> the async engine. For local development use
> `sqlite+aiosqlite:///./question_bank.db` instead.

## Layout

```
app/
  main.py            app factory, CORS, rate-limit middleware, lifespan, /health
  config.py          settings from env / .env
  db.py              async engine, per-request session, ensure_schema (SQLite upgrades)
  models.py          ORM — 8 tables: subjects, chapters, questions, papers,
                     paper_questions, practice_sessions, practice_session_questions, users
  errors.py          normalises every error to {"error", "detail"}
  security.py        scrypt password hashing, access / download / reset tokens
  ratelimit.py       sliding-window rate limits (in memory)
  deps.py            get_current_user
  schemas/           request + response models (incl. schemas/auth.py)
  routers/           auth, questions, papers, export, practice, syllabus
  services/          business logic; routers stay thin
    auth.py          accounts, login lockout, password reset, profile + preferences
    mailer.py        SMTP sender for reset emails (logs the link when SMTP is unset)
    generation.py    the bridge to Module A (caching + error mapping)
    blueprint.py     blueprint papers: allocation arithmetic + building the paper
    export/          HTML template, PDF renderers, file handling
assets/fonts/        Noto Sans + Noto Sans Kannada, used by the fpdf renderer
data/syllabus.json   interim chapter list (see data/README.md)
migrations/          Alembic (async env): 0001 schema, 0002 users, 0003 ownership,
                     0004 paper sections, 0005 user preferences, 0006 figures,
                     0007 answer verification, 0008 figure metadata
tests/               575 tests, no network and no real database
```

## Endpoints

All paths are under `/api/v1`. Everything needs a bearer token except sign-up, sign-in,
password reset, the download link, and `/health`.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/signup` | Create an account; returns a token (auto sign-in) |
| `POST` | `/auth/login` | Email + password → token. Locks an (IP, email) pair after repeated failures |
| `GET` `PATCH` | `/auth/me` | The signed-in user **with their preferences**. `PATCH` saves name, role and preferences; the **email can't be changed** (403) |
| `POST` | `/auth/forgot-password` | Emails a reset link. Same reply whether or not the account exists |
| `POST` | `/auth/reset-password` | `{token, password}` → sets a new password; the link is single-use |
| `POST` | `/generate` | Generate a batch. Serves from cache unless `"refresh": true` |
| `GET` | `/generation/combinations` | Which marks are valid for which question type |
| `GET` | `/questions` | Filter/search/paginate |
| `GET` `PATCH` `DELETE` | `/questions/{id}` | Fetch, curate, discard (only the creator can edit/discard) |
| `POST` `GET` | `/papers` | Create / list your papers |
| `GET` `PATCH` `DELETE` | `/papers/{id}` | Fetch, reorder, override marks, rename, delete |
| `POST` | `/papers/blueprint/preview` | How a blueprint splits marks across chapters (no LLM, no writes) |
| `POST` | `/papers/blueprint` | Build and save a paper from a blueprint |
| `POST` `GET` | `/papers/blueprint/jobs`, `/papers/blueprint/jobs/{id}` | The same build in the background: returns a job id at once, then reports `done` / `total` questions and finally the paper (what the Question Papers page uses for its progress bar). In-memory, one build per user at a time |
| `POST` `GET` | `/figures` | Upload a diagram (**administrators only**) / list the shared library (anyone signed in) |
| `GET` `PATCH` `DELETE` | `/figures/{id}` | Metadata; edit and delete are administrators only (`409` while in use). `GET /figures/{id}/file` is the image |
| `POST` | `/export/{paper_id}` | Render PDF, returns a signed `download_url` |
| `GET` | `/export/files/{filename}` | What `download_url` points at (short-lived signed token, no header needed) |
| `POST` | `/practice/sessions` | Start a session (answers withheld) |
| `GET` | `/practice/sessions/{id}` | Resume a session |
| `GET` | `/practice/sessions/{id}/reveal/{question_id}` | Reveal one answer |
| `GET` | `/subjects` | All five subjects |
| `GET` | `/subjects/{subject}/chapters` | Chapters + question counts |

Beyond the original contract: `GET /papers`, `GET /practice/sessions/{id}`,
`GET /generation/combinations`, blueprint papers, and everything under `/auth`.
`docs/api-contract.md` covers sign-up, sign-in and `/auth/me` but not yet password
reset, `PATCH /auth/me` or the blueprint endpoints; this README and `/docs` are the
current reference for those.

## Accounts, settings and password reset

**Passwords** are hashed with scrypt (standard library, no extra dependency); the cost
parameters are stored in the hash so they can be raised later. Sign-up requires 8+ characters
with a letter and a number. `Admin` is never assignable through the API.

**Sign-in lockout.** 5 wrong passwords for the same (IP, email) within 15 minutes blocks that pair
even if the next password is right. The email is part of the key, so a stranger can't lock someone
out from a different network.

**Password reset.**

1. `POST /auth/forgot-password {email}` — always returns 200 with the same message. The email is sent
   in a background task after the response, so neither the body nor the timing reveals whether the
   address has an account.
2. The email links to `FRONTEND_URL/reset-password?token=…`. The token is a signed JWT with a 30-minute
   lifetime (`PASSWORD_RESET_EXPIRE_MINUTES`) carrying a fingerprint of the *current* password hash.
3. `POST /auth/reset-password {token, password}` verifies the token and the fingerprint, then sets the new
   password. Because the fingerprint no longer matches afterwards, the link can't be used twice and
   there is no token table. A token that is expired, forged, already used, or an ordinary access token
   gets `400 invalid_reset_token`.

**Sending the email.** Set these in `backend/.env`; with `SMTP_HOST` empty nothing is sent and the link
is logged to the backend terminal instead (use that locally).

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<16-character app password>   # Google account -> Security -> App passwords
SMTP_FROM="KRIES <you@gmail.com>"           # use the same address as SMTP_USERNAME for Gmail
SMTP_SECURITY=starttls                      # starttls (587) | ssl (465) | none
FRONTEND_URL=https://your-frontend.example  # where reset links point; default http://localhost:5173
```

**Settings.** `PATCH /auth/me` takes any subset of `{name, role, preferences}`. `preferences` holds
`theme` (`light|dark|system`), `notifications`, `default_question_count` (3–30), `default_difficulty`,
`default_question_type` (`MCQ|Short|Long|Fill|Match|Mixed`) and `default_marks` (1, 2, 3 or 5); unsent keys are left alone, unknown keys are
rejected. They are stored as JSON in `users.preferences` (migration `0005`, also added by `ensure_schema`
for SQLite). An account that never saved anything is reported with the defaults. Sending `email`, or an
`Admin` changing their own role, returns 403.

## Rate limiting

All limits answer `429` with the usual error body and a `Retry-After` header. Each is `<requests>/<seconds>`
in `.env` (see `.env.example`); `RATE_LIMIT_ENABLED=false` turns them all off (the test suite does this).

| Bucket | Applies to | Default | Keyed by |
|---|---|---|---|
| `global` | every `/api` request | 120 / min | user (IP if signed out) |
| `login` | `POST /auth/login` | 10 / min | IP |
| `signup` | `POST /auth/signup` | 5 / hour | IP |
| `password-reset` | `/auth/forgot-password`, `/auth/reset-password` | 5 / 15 min | IP |
| `generate` | `/generate`, `/practice/sessions`, `/papers/blueprint` | 30 / min | user |
| `export` | `POST /export/{id}` | 10 / min | user |

Counters live in this process's memory: right for one uvicorn worker, but each worker or instance keeps
its own counts, so move them to Redis before scaling out. Set `TRUST_PROXY_HEADERS=true` only behind a
reverse proxy you control, otherwise clients could fake their IP.

## Design notes

**Errors.** Every failure comes back as `{"error": "...", "detail": "..."}`. A malformed request body maps
to **400**, not FastAPI's default 422 — the contract reserves 422 for *generated output* that failed
validation. Module A's exceptions map as its `exceptions.py` prescribes: `InvalidRequestError` → 400,
`GroqAPIError` → 502, `GenerationValidationError` → 422.

**Caching.** A repeated identical `/generate` is served from stored questions; only the shortfall goes to
Groq. `{"refresh": true}` forces fresh generation — that's what the "generate more" button sends. The
response carries `cached` and `generated` counts so the UI can say which is which.

**Nothing partial is stored.** Questions are written only after Module A returns a fully validated batch,
and the request-scoped transaction rolls back on any exception. Blueprint papers are one transaction too.

**Edits are re-validated.** `PATCH /questions/{id}` runs the edited question back through Module A's schema
and `check_marks_format`, so changing a question's marks or MCQ options can't leave it with an answer that no
longer fits. `subject`, `chapter` and `grade` are not editable, and **neither is `answer`**: a request that
includes it gets a 400. The key is verified at generation time, so it is read-only; generate the question
again to get a different one.

**Ownership.** Papers and practice sessions are filtered by owner on every endpoint, so one user can never
list, read, change, export or delete another's. The question pool is shared; only a question's creator can
edit or discard it. Rows created before sign-in existed have no owner and stay hidden.

**Soft deletes.** `DELETE /questions/{id}` flips `is_active` rather than removing the row, so papers and
practice sessions that reference the question stay intact.

**Practice answers are withheld at the model level.** The session response uses a separate schema with no
`answer` field at all, rather than blanking it.

**Paper totals are server-computed** from the questions, using `marks_override` where set. A client
`total_marks` that disagrees is a 400.

**Blueprint papers.** `services/blueprint.py` allocates marks to chapters deterministically (so the page can
preview it), fetches each section's questions through the same service as `/generate`, and stores the
section on `paper_questions.section` (migration `0004`). A blueprint paper holds at most 100 questions.

## PDF export

Three backends, selected by `PDF_RENDERER` (`auto` | `weasyprint` | `reportlab` | `fpdf`):

- **WeasyPrint** — preferred. Renders the HTML in `services/export/html.py` and shapes complex scripts
  correctly via Pango/HarfBuzz, which matters because **Kannada** is one of the five subjects. Needs system
  libraries:
  ```bash
  apt-get install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 \
                  libgdk-pixbuf-2.0-0 fonts-noto-core
  pip install -r requirements-pdf.txt
  ```
- **ReportLab** — always installed, no system dependencies, so it works on a bare Render/AWS container.
  Fine for the Latin-script subjects. If a Kannada paper reaches it with no Kannada font, it returns a 503
  explaining what to install rather than a PDF of empty boxes.
- **fpdf** — pure-pip (`fpdf2` + `uharfbuzz`, in `requirements.txt`), with Noto Sans and Noto Sans Kannada
  bundled in `assets/fonts`. It shapes Kannada correctly with no system libraries, so Kannada papers use it on
  Windows or any host without WeasyPrint. In `auto` mode Kannada goes to WeasyPrint if present, otherwise fpdf;
  ReportLab is never used for Kannada.

`auto` uses WeasyPrint when importable and falls back to ReportLab. `/health` reports which one is live.
Blueprint sections ("Section A … 10 marks") render in all three. The answer key is always included.

Exports are written to `EXPORT_DIR`; `POST /export/{id}` returns a link with a signed, 10-minute token bound to
that one file (a new browser tab can't send an Authorization header). On multi-instance AWS this should become S3
with a presigned URL — only `_write` and `public_url` in `services/export/__init__.py` would change.

## Figures

A question can carry a diagram: `figure_id` prints with the question, `answer_figure_id` prints only in the
answer key (set both with `PATCH /questions/{id}`; `null` detaches). When a question has no answer figure,
the answer key prints the question's own figure, so a generated diagram question shows its diagram in the key.

**Administrators manage the figure library; everyone uses it.** A user with the `Admin` role gets a
*Figure Library* page in the web app, where they upload a diagram and tag it with a subject, chapter,
optional topic, a caption and the labelled parts (`A: nucleus`, one per line). Every teacher can then tick
*Write questions about figures* on the Generate page and get diagram-based questions for that chapter; the
diagram is printed with the question in the paper and again in the answer key.

Only the admin-only routes change: `POST` / `PATCH` / `DELETE /figures` answer `403 admin_required` for
anyone else. The role is read from the account on every request. **It can't be self-assigned**: sign-up only
offers Teacher and Student, and `PATCH /auth/me` refuses `Admin`. Make the first administrator on the server
(the person signs up normally first, then):

```bash
python scripts/make_admin.py principal@school.in            # grant
python scripts/make_admin.py principal@school.in --demote   # back to Teacher
python scripts/make_admin.py --list
```

To load a folder of images at once instead of one at a time in the browser:

```bash
python scripts/upload_figure.py cell.png --admin principal@school.in \
  --subject Science --chapter "Cell - Structure and Functions" \
  --caption "Plant cell" --labels "A: nucleus" "B: cell wall"
```

To load a whole folder where each image has its own caption, chapter and labels, use a manifest. The 49 Science
diagrams in `backend/data/figures/` ship with one:

```bash
python scripts/upload_figure.py --manifest backend/data/figures/manifest.json --admin principal@school.in --dry-run
python scripts/upload_figure.py --manifest backend/data/figures/manifest.json --admin principal@school.in
```

Re-running skips figures whose subject, chapter and caption are already in the library (`--force` adds anyway).

Teachers and administrators see a figure's subject / chapter / topic / labels; students don't (the labels are
an answer key). The old `FIGURE_ADMIN_TOKEN` / `X-Admin-Token` mechanism is gone.

- **Storage:** files live in `FIGURE_DIR` (default `var/figures`), metadata in the `figures` table. Only
  `services/figures.py` touches the disk, so moving to S3 means changing that module.
- **Uploads are re-encoded, never stored as received:** the type is sniffed from the bytes (the client's
  file name and Content-Type are ignored), transparency is flattened onto white, EXIF/GPS is dropped, and the
  long side is capped at 2400 px. SVG is refused because it is code, not pixels. Limits: `MAX_FIGURE_BYTES`
  (5 MB) and `RATE_LIMIT_UPLOAD` (20/min per user).
- **Printing:** all three renderers draw figures at the same size (natural size at 150 dpi, shrunk to fit
  120 × 70 mm) with the caption underneath, and keep a figure on the same page as its question. A missing
  image file is logged and skipped rather than failing the export. An answer-key figure also earns the
  "Diagram" mark in the marks split.
- **Practice mode:** a student sees `figure` immediately but `answer_figure` only from the reveal endpoint.

### Questions about your figures

A figure can carry `subject`, `chapter`, `topic` and `labels` (e.g. `A: nucleus`). `POST /generate` with
`"use_figures": true` (or `"figure_ids": [...]`) writes each question about one of your figures: the model is given the
caption, topic and labels as text, names the figure by a short reference (`F1`), and the engine attaches the real
`figure_id`, so the model never sees the image or an id. Questions that contradict the metadata are dropped and
retried, and the answer-key verifier sees the same description. Labels are visible to the owner only and never travel
with a question. Setting: `MAX_GENERATION_FIGURES` (6). Migration `0008`. See `docs/api-contract.md`.
- **Identity:** a question's duplicate-detection hash includes its `figure_id`, so "Label the diagram" with two
  different diagrams is two questions.
- **Migration:** `0006` (batch mode, so it also runs on SQLite). `ensure_schema` covers dev databases.

## Answer-key verification

Generation does not check answer keys; it is an on-demand step, because the model that writes a question also writes
its answer key. After generating, the **Verify answers** button calls `POST /questions/verify`. Exact **rule checks**
(Maths/Science patterns, no LLM) run first, then an **independent AI pass** (one Groq call per chunk of questions; MCQs
are solved blind and compared with the key; Match keys are checked pair by pair). Each question carries
`verification_status` (`verified` / `unverified` / `flagged`) and `verification_note`; new questions start as
`unverified`. A key found wrong is marked `flagged`, not regenerated, and a flagged question is never served from the
cache or used in practice sessions. Settings: `ENABLE_ANSWER_RULE_CHECKS`, `ENABLE_LLM_ANSWER_VERIFICATION`,
`VERIFIER_MODEL`, `VERIFICATION_CHUNK_SIZE`. Migration `0007`. The full description is in
`docs/api-contract.md` (*Answer verification*) and `generation_engine/README.md`.

- The answer is read-only, so a `verified` badge always describes the stored answer. Editing a question's
  `text` or `options` still does not re-run verification.

## Syllabus data

`data/syllabus.json` ships a hand-curated, grade-scoped chapter list for the five subjects (see `data/README.md`),
loaded through `SYLLABUS_JSON_PATH` and seeded into the database at startup so the chapter picker isn't empty.
With a syllabus loaded, unknown chapters, and chapters outside the requested grade, are rejected with a 400. Leave `SYLLABUS_JSON_PATH=` empty to run without
one; chapters are then created on first use, case-insensitively. To replace the list with real textbook data use
`scripts/ingest_syllabus.py` (see the repo-root README).

**Textbook-grounded mode.** Ingest the KTBS PDFs with `scripts/ingest_textbooks.py` into `data/textbooks/`
(`TEXTBOOKS_DIR`). The syllabus is then derived from the textbooks for every (subject, grade) they cover, and
questions are written from their passages. `REQUIRE_TEXTBOOK=true` refuses any request with no ingested textbook
text and ignores `syllabus.json`; `REQUIRE_SYLLABUS=true` refuses generation when no syllabus is loaded;
`GROUNDING_MIN_OVERLAP` and `MAX_PASSAGE_CHARS` tune the grounding check. See `generation_engine/README.md`.
Figure requests (`use_figures`) are written from the figures' metadata and skip textbook grounding.

## Tests

```bash
cd backend && pytest          # 539 tests
cd .. && pytest               # Module A's 161 tests
```

In-memory SQLite and a stubbed Groq client, so no database or API key is needed. The suite covers every endpoint's
success and error paths, filters and pagination, the "no partial data stored" guarantee, caching, reorder and
marks-override persistence, answer masking, PDF byte checks (including Kannada), ownership between users, rate
limiting, sign-up/sign-in, password reset (single use, expiry, no account enumeration), profile and preference
saving, blueprint allocation, and upgrading an older database (`ensure_schema` and Alembic up/down).

Production runs on PostgreSQL. The models use portable column types with PostgreSQL variants (`jsonb`, `text[]`,
native enums) so the suite can run without one. It has **not** yet been run against a live PostgreSQL; do that before
deploying:

```bash
DATABASE_URL=postgresql+asyncpg://... pytest
```

## Still open

- `GET /questions` uses `LIKE` for search. Fine for MVP volumes; switch to a PostgreSQL `tsvector` index if the bank
  grows large.
- Exports are never cleaned up — add a retention job, or move to S3 lifecycle rules.
- Rate-limit counters are per process (see above).
- The answer key can't be left out of an exported PDF.
- Figures: uploaded images are not yet used by the generator itself (the LLM never sees them), and there is no
  shared figure library or crop/annotate tool. Orphaned files (an upload never attached) stay on disk until deleted.
- Reset emails have only been tested with a stubbed sender, not a real SMTP server.
- `docs/api-contract.md`, `docs/db-schema.md` and `docs/task-tracker.md` still describe the pre-auth design in places.

## Troubleshooting

**`socket.gaierror: [Errno 11001] getaddrinfo failed` at startup, and the frontend's chapter list never loads.**
The backend can't resolve the host in `DATABASE_URL`. Note that `backend/.env` overrides the repo-root `.env`.
For local development you don't need PostgreSQL. Set this in `backend/.env` and restart:

```
DATABASE_URL=sqlite+aiosqlite:///./question_bank.db
```

The file and tables are created automatically on startup. (`pip install aiosqlite` if it isn't installed.)
For PostgreSQL, use the `postgresql+asyncpg://` form, make sure the server is running, and run `alembic upgrade head`
(or set `AUTO_CREATE_TABLES=true`).

**The reset email never arrives.** With `SMTP_HOST` empty nothing is sent: look for "Password reset link for …" in the
backend log. With SMTP configured, the log shows the SMTP error; the usual causes are a wrong app password or an
`SMTP_FROM` that doesn't match the Gmail account.

**Everyone is signed out after every restart.** `JWT_SECRET` is unset, so a random key is generated per process. Set it
(`python -c "import secrets; print(secrets.token_urlsafe(48))"`).

**After upgrading, `no such column: users.preferences`.** Your database predates migration `0005`. SQLite adds the column on
startup; on PostgreSQL run `alembic upgrade head`.
