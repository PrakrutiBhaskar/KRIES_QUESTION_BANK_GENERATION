# KRIES Frontend

React + TypeScript + Vite + Tailwind, talking to the FastAPI backend in `../backend`.

## Run it

```bash
# 1. Backend (from the repo root) — needs GROQ_API_KEY in .env for real generation
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload          # http://localhost:8000

# 2. Frontend
cd frontend
cp .env.example .env
npm install
npm run dev                                    # http://localhost:5173
```

In dev, Vite proxies `/api` to `VITE_BACKEND_URL` (default `http://localhost:8000`), so no CORS
setup is needed. For a production build served from another origin, set `VITE_API_BASE_URL` to the
full API URL and add the site to `CORS_ORIGINS` in the backend `.env`.

## How the UI maps to the API

| UI | Backend |
|---|---|
| Subject / chapter pickers | `GET /subjects/{subject}/chapters` |
| Type → marks options | `GET /generation/combinations` |
| Generate | `POST /generate` (one call per type × difficulty when "Mixed") |
| Delete a generated question | `DELETE /questions/{id}` |
| Save Bank | `POST /papers` — a **question bank is a saved paper** |
| Bank list / detail | `GET /papers`, `GET /papers/{id}` |
| Remove question / add generated question | `PATCH /papers/{id}` (replaces the question list) |
| Delete bank | `DELETE /papers/{id}` |
| Export PDF | `POST /export/{id}` → opens `download_url` |

All calls live in `src/lib/api.ts`. Sign up / sign in use `POST /auth/signup`, `POST /auth/login` and `GET /auth/me`; the JWT is sent as a bearer token on every request.

## Not in the backend yet (removed from the UI)

Bloom's taxonomy level, bank description, and draft/published/archived status have no backend
field, so those controls were removed rather than faked.
