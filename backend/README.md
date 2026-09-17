# Backend — Module B

FastAPI + PostgreSQL service for the Question Bank Generator. Implements
every endpoint in [`docs/api-contract.md`](../docs/api-contract.md) against
the schema in [`docs/db-schema.md`](../docs/db-schema.md), and calls Module A
(`generation_engine/`) for generation.

## Quick start

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r ../requirements.txt -r requirements.txt

cp .env.example .env          # set DATABASE_URL; GROQ_API_KEY goes in the repo-root .env
createdb question_bank_db
alembic upgrade head

uvicorn app.main:app --reload
```

Interactive docs at <http://localhost:8000/docs>, health check at `/health`.

> **`DATABASE_URL` needs the `+asyncpg` driver** —
> `postgresql+asyncpg://user:pass@host:5432/question_bank_db`. A bare
> `postgresql://` URL fails at startup, because both the app and Alembic use
> the async engine.

## Layout

```
app/
  main.py            app factory, CORS, lifespan, /health
  config.py          settings from env / .env
  db.py              async engine + per-request session
  models.py          ORM — the 7 tables in db-schema.md
  errors.py          normalises every error to {"error", "detail"}
  schemas/           request + response models
  routers/           questions, papers, export, practice, syllabus
  services/          business logic; routers stay thin
    generation.py    the bridge to Module A (caching + error mapping)
    export/          HTML template, PDF renderers, file handling
migrations/          Alembic (async env, initial schema)
tests/               79 tests, no network and no real database
```

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/generate` | Generate a batch. Serves from cache unless `"refresh": true` |
| `GET` | `/api/v1/questions` | Filter/search/paginate |
| `GET` `PATCH` `DELETE` | `/api/v1/questions/{id}` | Fetch, curate, discard |
| `POST` `GET` | `/api/v1/papers` | Create / list papers |
| `GET` `PATCH` | `/api/v1/papers/{id}` | Fetch, reorder, override marks, rename |
| `POST` | `/api/v1/export/{paper_id}` | Render PDF, returns `download_url` |
| `GET` | `/api/v1/export/files/{filename}` | What `download_url` points at |
| `POST` | `/api/v1/practice/sessions` | Start a session (answers withheld) |
| `GET` | `/api/v1/practice/sessions/{id}` | Resume a session |
| `GET` | `/api/v1/practice/sessions/{id}/reveal/{question_id}` | Reveal one answer |
| `GET` | `/api/v1/subjects` | All five subjects |
| `GET` | `/api/v1/subjects/{subject}/chapters` | Chapters + question counts |

Two additions beyond the contract, both backwards-compatible: `GET /papers`
(the frontend's paper list needs it) and `GET /practice/sessions/{id}` (so a
student can resume a session rather than restarting it).

## Design notes

**Errors.** Every failure comes back as `{"error": "...", "detail": "..."}`.
A malformed request body maps to **400**, not FastAPI's default 422 — the
contract reserves 422 for *generated output* that failed validation. Module
A's exceptions map as its `exceptions.py` prescribes: `InvalidRequestError`
→ 400, `GroqAPIError` → 502, `GenerationValidationError` → 422.

**Caching.** A repeated identical `/generate` is served from stored
questions; only the shortfall goes to Groq. `{"refresh": true}` forces fresh
generation — that's what the teacher's "generate more" button should send.
The response carries `cached` and `generated` counts so the UI can say which
is which.

**Nothing partial is stored.** Questions are written only after Module A
returns a fully validated batch, and the request-scoped transaction rolls
back on any exception. Covered by tests on all three error paths.

**Edits are re-validated.** `PATCH /questions/{id}` runs the edited question
back through Module A's schema and `check_marks_format`, so a 3-mark answer
can't be hand-edited down to one line. `subject`, `chapter` and `grade` are
not editable — changing them would invalidate the rules the question was
generated under.

**Soft deletes.** `DELETE /questions/{id}` flips `is_active` rather than
removing the row, so papers and practice sessions that already reference the
question stay intact. Every read path filters it out; a second delete 404s.

**Practice answers are withheld at the model level.** The session response
uses a separate schema with no `answer` field at all, rather than blanking
it — the key can't leak through a serialization slip.

**Paper totals are server-computed** from the questions, using
`marks_override` where set. If the client sends a `total_marks` that
disagrees, that's a 400 rather than a silent overwrite.

## PDF export

Two backends, selected by `PDF_RENDERER` (`auto` | `weasyprint` | `reportlab`):

- **WeasyPrint** — preferred. Renders the HTML in `services/export/html.py`
  and shapes complex scripts correctly via Pango/HarfBuzz. This matters
  because **Kannada** is one of the five subjects: its script needs glyph
  reordering and ligature substitution that simpler PDF writers don't do.
  Needs system libraries:
  ```bash
  apt-get install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 \
                  libgdk-pixbuf-2.0-0 fonts-noto-core
  pip install -r requirements-pdf.txt
  ```
- **ReportLab** — always installed, no system dependencies, so it works on a
  bare Render/AWS container. Fine for the Latin-script subjects. If a Kannada
  paper hits this backend with no Kannada font registered, it returns a 503
  explaining what to install rather than emitting a PDF of empty boxes.

`auto` uses WeasyPrint when importable and falls back to ReportLab. `/health`
reports which one is live.

Exports are written to `EXPORT_DIR` and served from
`/api/v1/export/files/{filename}`. On multi-instance AWS this should become
S3 with a presigned URL — only `_write` and `public_url` in
`services/export/__init__.py` would change.

## Syllabus data

Chapter ingestion is still open (spec.md Section 8). Until it lands, chapters
are created on first use, normalised case-insensitively so
`photosynthesis` and `Photosynthesis` don't become two separate banks.

Once the PDF-parsing pipeline produces chapter JSON in
`generation_engine.syllabus.SyllabusIndex`'s shape, set
`SYLLABUS_JSON_PATH`. The backend then hands the index to the engine, and
unknown chapters start returning 400 — no code change needed.

## Tests

```bash
cd backend && pytest          # 79 tests
cd .. && pytest               # Module A's 121 tests
```

The suite uses in-memory SQLite and a stubbed Groq client, so it needs
neither a database nor an API key. Coverage maps to test-plan.md Section 2:
every endpoint's success path, all filter combinations, pagination, the
400/404/422/502 error paths, the "no partial data stored" guarantee, cache
hit/miss/shortfall, reorder and marks-override persistence, answer masking,
and a real PDF byte-check (including a 25-question paper for Section 5's
layout case).

Production runs on PostgreSQL. The models use portable column types with
PostgreSQL variants (`jsonb`, `text[]`, native enums) so the suite can run
without a live database while production keeps the schema in db-schema.md.
Run the suite against real PostgreSQL before deploying:

```bash
DATABASE_URL=postgresql+asyncpg://... pytest
```

## Still open

- `GET /questions` uses `LIKE` for search. Fine for MVP volumes; switch to a
  PostgreSQL `tsvector` index if the bank grows large.
- Exports are never cleaned up — add a retention job, or move to S3 lifecycle
  rules.
- Rate limiting and `user_id` scoping arrive with auth (ADR 5); the nullable
  columns are already in place.
