# KRIES Frontend

React 19 + TypeScript + Vite + Tailwind CSS 4, talking to the FastAPI backend in `../backend`.

## Run it

```bash
# 1. Backend (from the repo root) — needs GROQ_API_KEY in .env for real generation
pip install -r requirements.txt -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload     # http://localhost:8000

# 2. Frontend
cd frontend
cp .env.example .env
npm install
npm run dev                                     # http://localhost:5173
```

Other scripts: `npm run build` (type-checks, then builds), `npm run lint` (oxlint), `npm run preview`.

In dev, Vite proxies `/api` to `VITE_BACKEND_URL` (default `http://localhost:8000`), so no CORS setup is needed. For a
production build served from another origin, set `VITE_API_BASE_URL` to the full API URL and add the site to
`CORS_ORIGINS` in the backend `.env`. Password-reset emails link to the backend's `FRONTEND_URL`, so set that to the
site's real address too.

## Pages

| Route | Page |
|---|---|
| `/login`, `/signup` | Sign in / create an account (Teacher or Student) |
| `/forgot-password` | Ask for a reset email (same confirmation whether or not the account exists, with a resend timer) |
| `/reset-password?token=…` | Choose a new password from the emailed link; shows "Link expired" for a bad, used or expired link |
| `/dashboard` | Overview of your question banks |
| `/generate` | Generate questions for a subject/chapter, edit or discard them, save as a bank. Open to students too: they get stored questions first and a daily limit on new ones, and don't see Regenerate / Add Question / Verify answers (those always call the AI) |
| `/question-papers` | Build a board-style paper from a blueprint (chapter weightage + sections); students too, from the stored bank first |
| `/question-banks`, `/question-banks/:id` | Browse, rename, edit, delete and export saved banks |
| `/settings` | Profile and preferences (below) |

Everything except the first four pages needs you to be signed in; signed-out visitors are sent to `/login`.

## How the UI maps to the API

| UI | Backend |
|---|---|
| Sign up / sign in | `POST /auth/signup`, `POST /auth/login` |
| Stay signed in on reload | `GET /auth/me` (validates the stored token; a 401 signs you out) |
| Forgot / reset password | `POST /auth/forgot-password`, `POST /auth/reset-password` |
| Settings → Save | `PATCH /auth/me` (name, role, preferences) |
| Subject / chapter pickers | `GET /subjects/{subject}/chapters` |
| Type → marks options | `GET /generation/combinations` |
| Generate | `POST /generate` (one call per type × difficulty when "Mixed") |
| Verify answers (button, after generating) | `POST /questions/verify` |
| Delete a generated question | `DELETE /questions/{id}` |
| Save Bank | `POST /papers` — a **question bank is a saved paper** |
| Bank list / detail | `GET /papers`, `GET /papers/{id}` |
| Remove question / add generated question | `PATCH /papers/{id}` (replaces the question list) |
| Delete bank | `DELETE /papers/{id}` |
| Question Papers → live preview | `POST /papers/blueprint/preview` |
| Question Papers → Build | `POST /papers/blueprint` |
| Export PDF | `POST /export/{id}` → opens `download_url` |

All calls live in `src/lib/api.ts`. The JWT is sent as a bearer token on every request; "Keep me signed in" keeps it in
`localStorage`, otherwise in `sessionStorage`. A 401 on any authenticated call clears the session and returns to sign-in.

## Settings

- **Profile** — change your name and switch between Teacher and Student. The **email is read-only** (it is your sign-in);
  an Admin's role is locked too.
- **Preferences** — theme (Light / Dark / System), in-app notifications, and the generation defaults (question count,
  difficulty, type, marks per question). The Generate and Question Papers pages start from these.
- **Account** — sign out, and reset preferences to their defaults.

**Saving.** Nothing is saved until you press *Save Changes* (disabled until something changed); it sends only what changed
to `PATCH /auth/me`, so it is stored in the database and follows you to other devices. Server errors show inline. *Reset
Preferences* saves immediately. The preferences are also cached in `localStorage` (`kries_settings`) purely so the theme is
right before the first request returns.

**Theme.** Picking a theme previews it immediately; if you leave Settings without saving, it reverts. The `dark` class is
put on `<html>` by `src/lib/theme.ts` (and by a small script in `index.html` so there is no white flash on load); *System*
follows the OS and updates live. The app is written with light-mode Tailwind classes, so dark mode works by redefining the
palette in `src/index.css` instead of touching each page. If you add a surface that should stay dark in both themes (like
the sidebar), give it the `theme-static` class. Turning notifications off hides success/info pop-ups; errors always show.

## Source layout

```
src/
  App.tsx            routes
  pages/             one file per route
  components/        Sidebar, Header, AuthShell (shared sign-in layout + fields), toasts, shared UI
  layouts/           AppLayout — the signed-in shell
  hooks/useApp.tsx   app state: user, preferences, banks, toasts; saveProfile()
  lib/api.ts         typed API client (wire snake_case <-> app camelCase)
  lib/auth.ts        session + preference storage, defaults
  lib/theme.ts       applies Light / Dark / System
  types/index.ts     shared types
```

## Not in the backend yet (removed from the UI)

Bloom's taxonomy level, bank description, and draft/published/archived status have no backend field, so those controls were
removed rather than faked. The prototype's mock-data files were deleted. There is no Analytics page.

## Not done

No automated UI tests, no CI job for the frontend, no Android build, and the app isn't deployed anywhere yet.
