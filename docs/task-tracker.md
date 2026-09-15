# Task Tracker — GitHub Projects Setup

## Board setup
Create a GitHub Projects (board view) with columns:
`Backlog → In Progress → In Review → Done`

Label tasks by module: `module:generation`, `module:backend`, `module:frontend`, `module:docs`.

## Sprint 1 — Generation Engine
- [x] Define finalized prompt template — MCQ
- [x] Define finalized prompt template — Short answer (marks-aware: 1, 2, 3)
- [x] Define finalized prompt template — Long answer (marks-aware: 5)
- [x] Implement Groq API call wrapper (retry/backoff on 429 and 5xx, JSON response mode)
- [x] Implement output validation (schema, duplicate check, marks-length check)
- [x] Implement batch generation logic (retry-to-fill, rejection reasons fed back into the retry prompt)
- [x] Write test cases for generation output (see test-plan.md) — 100 tests
- [ ] Syllabus ingestion: pick the PDF-parsing tool and produce chapter JSON. `SyllabusIndex.from_json` is the drop-in point; until then chapter validation is skipped and any non-blank chapter is accepted.
- [ ] Tune `NEAR_DUPLICATE_SIMILARITY_THRESHOLD` (currently 0.90) against real generated batches
- [ ] Manual factual spot-check per subject (test-plan.md Section 4) — needs a live Groq key

## Sprint 2 — Backend
- [ ] Set up FastAPI project structure
- [ ] Create PostgreSQL schema + migrations (see db-schema.md)
- [ ] Implement `POST /generate`
- [ ] Implement `GET /questions`, `PATCH /questions/{id}`, `DELETE /questions/{id}`
- [ ] Implement `POST /papers`, `GET /papers/{id}`, `PATCH /papers/{id}`
- [ ] Implement `POST /export/{paper_id}` (PDF generation)
- [ ] Implement `POST /practice/sessions`, reveal endpoint
- [ ] Implement `GET /subjects`, `GET /subjects/{subject}/chapters`
- [ ] Add caching for repeated generation requests

## Sprint 3 — Frontend
- [ ] Set up React Native project (web + Android targets)
- [ ] Build subject/chapter selector screen
- [ ] Build generation request screen (type, marks, difficulty, count)
- [ ] Build question bank browser (search/filter/edit/discard)
- [ ] Build paper builder screen (select, reorder, assign marks, preview)
- [ ] Build practice mode screen (attempt, reveal)
- [ ] Wire up PDF export/download
- [ ] Connect all screens to backend API contract

## Cross-cutting (assign as needed)
- [ ] Syllabus PDF parsing pipeline → structured chapter/topic data
- [ ] Deploy backend (AWS or Render)
- [ ] Deploy frontend (web hosting + Android build)
- [ ] Write final report / demo prep

## Notes
- Each task should be assigned to one owner but reviewed by another team member before merging (keeps knowledge shared across the team).
- Link each PR to its task for traceability — useful for showing individual contribution later.
