# KRIES Frontend

A polished, production-quality frontend for the **KRIES Question Bank Generation System** — built with React, TypeScript, Vite, and Tailwind CSS.

> **Note:** This is a standalone frontend demo that uses local mock data only. No backend connection is required.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | React 19 + TypeScript |
| Build tool | Vite 8 |
| Styling | Tailwind CSS v4 |
| Routing | React Router v7 |
| Charts | Recharts |
| Icons | Lucide React |
| State | React Context + localStorage |

---

## Getting Started

```bash
cd frontend
npm install
npm run dev
```

Opens at **http://localhost:5173/**

### Login Credentials

> Any email + password works (demo mode).

Pre-filled credentials:
- **Email:** `priya.sharma@school.edu.in`
- **Password:** `password123`

---

## Routes

| Route | Description |
|---|---|
| `/login` | Login page |
| `/dashboard` | Overview, stats, recent activity |
| `/generate` | AI-powered question generation form |
| `/question-banks` | List, search, filter, and manage banks |
| `/question-banks/:id` | Detail view with all questions |
| `/analytics` | Charts and usage insights |
| `/settings` | Profile, preferences, generation defaults |

---

## Project Structure

```
src/
  components/     Shared UI components (badges, modals, sidebar, header)
  data/           Mock data (syllabus, question banks, analytics)
  hooks/          App context (auth, question banks, settings, toast)
  layouts/        AppLayout with responsive sidebar
  lib/            Auth, storage, generator, utils
  pages/          One file per route
  types/          TypeScript domain types
```

---

## Features

- ✅ Mock login/logout (localStorage)
- ✅ Dashboard with stats, charts, recent activity
- ✅ Generate page — configurable form + mock AI generation
- ✅ Edit / Delete / Reorder / Add questions
- ✅ Question Banks — grid & list view, search, filters, sort
- ✅ Question Bank Detail — full question list with CRUD
- ✅ Analytics — area, bar, pie, radar charts
- ✅ Settings — profile, preferences, generation defaults, theme
- ✅ Persistent state via localStorage (survives refresh)
- ✅ Toast notifications
- ✅ Confirmation modals
- ✅ Responsive layout (mobile sidebar, scrollable tables)
- ✅ No backend calls — completely standalone

---

## Domain

- **Board:** Karnataka State Board
- **Grades:** 7 · 8 · 9
- **Subjects:** Math · Science · Social Science · English · Kannada
- **Question Types:** MCQ · Short Answer · Long Answer
- **Bloom's Taxonomy:** Remember · Understand · Apply · Analyse · Evaluate · Create
- **Marks:** 1 · 2 · 3 · 5 (marks-aware answer formatting)
