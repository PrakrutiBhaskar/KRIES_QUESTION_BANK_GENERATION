# Question Bank Generator (KRIES)

AI-powered question bank generator for the Karnataka State Board (grades 7–9). Generates chapter-wise MCQ, short-answer, long-answer, fill-in-the-blank and match-the-following questions with marks-scheme-aware answer keys and difficulty tagging, lets teachers assemble question banks and blueprint-based question papers, and exports them as PDF (including Kannada, with or without the answer key). Includes sign-up/sign-in with Teacher, Student and Admin roles, password reset, per-user settings, an admin-managed figure library for diagram questions, and on-demand answer-key verification.

The repo-root `README.md` is the main entry point; this folder holds the design documents.

## Tech stack
- **Frontend:** React + TypeScript + Vite + Tailwind (web). An Android build (React Native) was the original plan and is still open
- **Backend:** Python (FastAPI), SQLAlchemy, Alembic
- **Database:** PostgreSQL (SQLite for local development)
- **LLM API:** Groq
- **Hosting:** AWS (or Render as fallback) — not decided or deployed yet

## Project structure
```
/generation_engine   # Module A: prompts → Groq → validated questions
/backend             # Module B: FastAPI service
  /app
    /routers         # API endpoints (auth, questions, figures, papers, export, practice, syllabus)
    /services        # business logic (generation bridge, blueprint papers, figures, PDF export, mailer)
    /schemas         # request/response models
    models.py        # DB models (9 tables)
  /migrations        # Alembic migrations (0001–0009)
  /data              # syllabus.json, figures/, model_papers/, textbooks/ (see backend/data/README.md)
  /scripts           # bulk_generate.py (+ bulk/), seed_figures.py, seed_model_papers.py
/frontend            # Module C: React web app (see frontend/README.md for the current build problem)
/scripts             # smoke_generate.py, ingest_syllabus.py, ingest_textbooks.py, make_admin.py,
                     # upload_figure.py, check_figures.py
/tests               # Module A's tests (backend tests are in /backend/tests)
/docs                # Project docs (this folder)
```

## Getting started

Full instructions are in the repo-root `README.md`. In short:

```bash
# Backend (local dev uses SQLite, no database server needed)
cd backend
python -m venv venv && source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r ../requirements.txt -r requirements.txt
# create backend/.env: JWT_SECRET (any long random string) is enough for local dev; add GROQ_API_KEY
# here or in the repo-root .env to generate. Every setting is defined in app/config.py.
uvicorn app.main:app --reload                        # http://localhost:8000/docs

# Frontend
cd frontend
cp .env.example .env
npm install
npm run dev                                          # http://localhost:5173
```

PostgreSQL instead of SQLite: set `DATABASE_URL=postgresql+asyncpg://…` and run `alembic upgrade head` from `backend/`.

## Environment variables (most important)
| Variable | Description |
|---|---|
| `GROQ_API_KEY` | API key for Groq |
| `DATABASE_URL` | `sqlite+aiosqlite:///./question_bank.db` (dev) or `postgresql+asyncpg://…` |
| `JWT_SECRET` | Signing key for access tokens; required in production |
| `FRONTEND_URL` | Where password-reset links point (default `http://localhost:5173`) |
| `SMTP_HOST` … `SMTP_SECURITY` | Outgoing email for password reset; leave `SMTP_HOST` empty in dev and the link is logged instead |
| `CORS_ORIGINS` | Allowed browser origins in production |
| `RATE_LIMIT_*`, `LOGIN_MAX_FAILURES` | Rate limits (defaults listed in `backend/README.md`) |
| `STUDENT_MAX_NEW_QUESTIONS_PER_REQUEST`, `STUDENT_MAX_NEW_QUESTIONS_PER_DAY` | Caps on what students may have generated (10 and 30) |
| `FIGURE_DIR`, `MAX_FIGURE_BYTES` | Where figure images are stored, and the upload size limit |
| `REQUIRE_TEXTBOOK`, `REQUIRE_SYLLABUS` | Refuse generation without ingested textbook text / a loaded syllabus |

The full list, with defaults, is in `backend/app/config.py` (backend) and `generation_engine/config.py` (engine). Only `frontend/.env.example` exists as an example file at the moment.

## Docs
- `project-context.md` — condensed brief; start here
- `spec.md` — full project spec
- `api-contract.md` — endpoint reference (password reset, `PATCH /auth/me` and the blueprint endpoints are documented in `backend/README.md` for now)
- `db-schema.md` — database schema (the `users` table and `users.preferences` are described in `backend/README.md`)
- `adr.md` — architecture decisions
- `prompt-library.md` — finalized LLM prompts
- `test-plan.md` — test cases
- `ui-wireframes.md` — planned screens
- `task-tracker.md` — sprint board
- `final-report-template.md` — template for the final project report

`api-contract.md`, `db-schema.md` and `task-tracker.md` lag the code in places. Where they disagree, the repo-root README,
`backend/README.md` and the interactive docs at `/docs` on a running backend are the current reference.

## Team
3-person team — see GitHub Projects board for task assignments and sprint plan.
