# Question Bank Generator

AI-powered question bank generator for the Karnataka State Board (grades 7–9). Generates chapter-wise MCQ, short-answer, and long-answer questions with marks-scheme-aware answer keys, difficulty tagging, and PDF export. Built for both web and Android from a single React Native codebase.

## Tech stack
- **Frontend:** React Native (Web + Android)
- **Backend:** Python (FastAPI)
- **Database:** PostgreSQL
- **LLM API:** Groq
- **Hosting:** AWS (or Render as fallback)

## Project structure
```
/frontend        # React Native app (web + Android)
/backend         # FastAPI service
  /app
    /routers     # API endpoints
    /models      # DB models
    /generation  # Groq prompt logic, validation
  /migrations    # DB schema migrations
/docs            # Project docs (spec, API contract, schema, ADRs, etc.)
```

## Getting started

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # add your Groq API key and DB connection string
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run web       # run in browser
npm run android   # run on Android emulator/device
```

### Database
```bash
# create the PostgreSQL database
createdb question_bank_db

# run migrations
cd backend
alembic upgrade head
```

## Environment variables
| Variable | Description |
|---|---|
| `GROQ_API_KEY` | API key for Groq |
| `DATABASE_URL` | PostgreSQL connection string |

## Docs
See `/docs` for:
- `spec.md` — full project spec
- `api-contract.md` — endpoint reference
- `db-schema.md` — database schema
- `adr.md` — architecture decisions
- `prompt-library.md` — finalized LLM prompts
- `test-plan.md` — test cases

## Team
3-person team — see GitHub Projects board for task assignments and sprint plan.
