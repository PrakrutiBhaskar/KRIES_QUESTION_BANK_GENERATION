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

Other scripts: `npm run build` (type-checks, then builds), `npm run lint` (oxlint: 0 errors, 7 warnings), `npm run preview`.

> **`npm run build` currently fails.** `tsc -b` reports 42 type errors, all in seven leftover prototype files
> that no live code imports (see [Leftover prototype files](#leftover-prototype-files-break-the-build)).
> `npm run dev` is unaffected because Vite does not type-check.

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
| `/generate` | Generate questions for a subject/chapter in any of the five types (MCQ, Short, Long, Fill, Match), edit or discard them, verify answer keys, save as a bank. Diagram-based questions are mixed in where the figure library has a match. Open to students too: they get stored questions first and a daily limit on new ones, and don't see Regenerate / Add Question / Verify answers (those always call the AI) |
| `/question-papers` | Build a board-style paper from a blueprint (chapter weightage + sections), with a live marks preview and a progress bar while it builds; students too, from the stored bank first |
| `/question-banks`, `/question-banks/:id` | Browse, rename, edit, delete and export saved banks. Export asks whether to include the answer key, so a student copy is one click. Diagrams show with the question and in the answer key |
| `/figure-library` | **Administrators only** (non-admins are redirected to `/dashboard`; the backend enforces it too): upload, tag, edit and delete the shared diagrams |
| `/settings` | Profile and preferences (below) |

Everything except the first four pages needs you to be signed in; signed-out visitors are sent to `/login`. The
Figure Library link only appears in the sidebar for administrators. There is no screen for practice sessions yet
(the backend API exists).

## How the UI maps to the API

| UI | Backend |
|---|---|
| Sign up / sign in | `POST /auth/signup`, `POST /auth/login` |
| Stay signed in on reload | `GET /auth/me` (validates the stored token; a 401 signs you out) |
| Forgot / reset password | `POST /auth/forgot-password`, `POST /auth/reset-password` |
| Settings → Save | `PATCH /auth/me` (name, role, preferences) |
| Subject / chapter pickers | `GET /subjects/{subject}/chapters` |
| Type → marks options | `GET /generation/combinations` |
| Generate | `POST /generate` (one call per type × difficulty when "Mixed"; sends `mix_figures` so some questions are diagram-based) |
| Verify answers (button, after generating) | `POST /questions/verify` |
| Edit a generated question | `PATCH /questions/{id}` |
| Delete a generated question | `DELETE /questions/{id}` |
| Figure Library (admin): list / upload / edit / delete | `GET`, `POST /figures`, `PATCH`, `DELETE /figures/{id}` |
| Figure images | `GET /figures/{id}/file` |
| Save Bank | `POST /papers` — a **question bank is a saved paper** |
| Bank list / detail | `GET /papers`, `GET /papers/{id}` |
| Remove question / add generated question | `PATCH /papers/{id}` (replaces the question list) |
| Delete bank | `DELETE /papers/{id}` |
| Question Papers → live preview | `POST /papers/blueprint/preview` |
| Question Papers → Build | `POST /papers/blueprint/jobs`, then polls `GET /papers/blueprint/jobs/{id}` for progress (`POST /papers/blueprint` is the single-call form) |
| Export PDF | `POST /export/{id}` with `include_answer_key` → opens `download_url` |

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
  components/        Sidebar, Header, AuthShell (shared sign-in layout + fields), RequireAdmin (route guard),
                     FigureImage, Skeleton, toasts, shared UI (ui.tsx, including the export dialog)
  layouts/           AppLayout — the signed-in shell
  hooks/useApp.tsx   app state: user, preferences, banks, toasts; saveProfile()
  lib/api.ts         typed API client (wire snake_case <-> app camelCase)
  lib/auth.ts        session + preference storage, defaults
  lib/theme.ts       applies Light / Dark / System
  types/index.ts     shared types
```

## Not in the backend yet (removed from the UI)

Bloom's taxonomy level, bank description, and draft/published/archived status have no backend field, so those controls were
removed from the live pages rather than faked. There is no Analytics page in the app: it is not routed or linked.

## Leftover prototype files break the build

Seven files from the original mock-data prototype were never deleted and no longer compile. Nothing in the live app imports
them (only each other), which is why `npm run dev` works while `npm run build` does not:

```
src/pages/AnalyticsPage.tsx
src/data/mockData.ts   src/data/syllabus.ts   src/data/analytics.ts
src/lib/analytics.ts   src/lib/generator.ts   src/lib/storage.ts
```

They use types and API helpers that were removed (Bloom's level, bank description, `fetchAllQuestions`, `StatCard`) and the
`recharts` package, which is not in `package.json`. Deleting them is the fix: with them removed, `tsc -b` passes and
`vite build` produces the bundle. If you do want an Analytics page back, rebuild it against the real API and add `recharts`.

## Not done

The build fix above, automated UI tests, a CI job for the frontend, an Android build, a screen for practice sessions, and
deployment: the app isn't hosted anywhere yet.
