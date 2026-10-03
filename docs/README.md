# Question Bank Generator (KRIES)

AI-powered question bank generator for the Karnataka State Board (grades 7–9). Generates chapter-wise MCQ, short-answer and long-answer questions with marks-scheme-aware answer keys and difficulty tagging, lets teachers assemble question banks and blueprint-based question papers, and exports them as PDF (including Kannada). Includes sign-up/sign-in, password reset and per-user settings.

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
    /routers         # API endpoints (auth, questions, papers, export, practice, syllabus)
    /services        # business logic (generation bridge, blueprint papers, PDF export, mailer)
    /schemas         # request/response models
    models.py        # DB models
  /migrations        # Alembic migrations (0001–0005)
  /data              # interim syllabus.json
/frontend            # Module C: React web app
/scripts             # smoke_generate.py, ingest_syllabus.py
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
cp .env.example .env          # add GROQ_API_KEY (repo-root .env or backend/.env); set JWT_SECRET for real deployments
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
| `RATE_LIMIT_*`, `LOGIN_MAX_FAILURES` | Rate limits (see `backend/.env.example`) |

The full list, with comments, is in `backend/.env.example` and the repo-root `.env.example`.

## Docs
- `spec.md` — full project spec
- `api-contract.md` — endpoint reference (password reset, `PATCH /auth/me` and the blueprint endpoints are documented in `backend/README.md` for now)
- `db-schema.md` — database schema (the `users` table and `users.preferences` are described in `backend/README.md`)
- `adr.md` — architecture decisions
- `prompt-library.md` — finalized LLM prompts
- `test-plan.md` — test cases
- `ui-wireframes.md` — planned screens
- `task-tracker.md` — sprint board

## Team
3-person team — see GitHub Projects board for task assignments and sprint plan.
