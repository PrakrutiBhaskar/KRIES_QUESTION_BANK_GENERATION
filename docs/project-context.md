# Project Context: Question Bank Generator

*This document is a self-contained brief for any LLM assisting with this project — paste it in as context before asking for help with code, prompts, docs, or debugging.*

## What this project is
An AI-powered question bank generator for the **Karnataka State Board, grades 7–9**. It generates syllabus-aligned practice questions (MCQ, short answer, long answer) with answer keys, difficulty tagging, and marks-scheme-aware answer formatting. Teachers use it to build question papers; students use it for self-study practice. Built by a 3-person team.

## Locked decisions

| Area | Decision |
|---|---|
| Board / Grades | Karnataka State Board, grades 7–9 |
| Subjects | Math, Science, Social Science, English, Kannada |
| Question types | MCQ, Short answer, Long answer |
| LLM API for generation | Groq |
| Frontend | React Native — single codebase for Web + Android |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Auth | Not in MVP — deferred, schema allows adding it later |
| Syllabus data source | Parsed from textbook PDFs |
| Hosting | AWS preferred, Render as fallback |
| MVP scope | Full app: generation, paper builder, practice mode, export |
| Task tracking | GitHub Projects |

## Core data model

All modules build against this shared `Question` object:

```json
{
  "id": "uuid",
  "subject": "Math | Science | Social Science | English | Kannada",
  "chapter": "string",
  "type": "MCQ | Short | Long",
  "text": "string",
  "options": ["string"],
  "answer": "string",
  "explanation": "string",
  "marks": 1,
  "difficulty": "easy | medium | hard",
  "topic": "string",
  "tags": ["string"]
}
```

Syllabus hierarchy: `Subject → Chapter → Questions`. `topic` is a tag on each question's answer key (describing the sub-topic within the chapter) — it is not a separate hierarchy level.

## The most important domain rule: marks-aware answers

Answer depth/format must match the marks allotted, mirroring how a real Karnataka State Board exam evaluates answers:

| Marks | Expected answer format |
|---|---|
| 1 | Single word/phrase, no explanation |
| 2 | 1–2 lines with one supporting point |
| 3 | Exactly 3 distinct points or steps |
| 5 | Detailed, multi-point/step answer, structured like a full exam response |

This mapping is subject-specific: Math's 5-mark answers need step-by-step derivations; Social Science's need distinct labeled sections (e.g. causes/effects); Science should reference diagrams/examples where relevant. MCQs always get a correct option + 1-line justification, regardless of marks.

Prompts should give the model explicit structure (e.g. "answer in 3 sections: X, Y, Z") rather than relying on it to infer structure from the mark value alone.

## System architecture (3 modules, one per team member)

1. **Generation Engine** — syllabus-structured prompts → Groq API → validated `Question` JSON output (schema check, duplicate check, marks-vs-answer-length check)
2. **Backend (FastAPI + PostgreSQL)** — stores questions/papers/practice sessions; exposes REST API for generation, retrieval, paper building, export, practice sessions
3. **Frontend (React Native)** — subject/chapter selection, generation request UI, question bank browser, paper builder (teacher), practice mode (student), PDF export

## Key API endpoints
- `POST /generate` — generate a batch of questions
- `GET /questions` — filter/search stored questions
- `POST /papers`, `PATCH /papers/{id}` — build/edit a question paper
- `POST /export/{paper_id}` — export paper as PDF
- `POST /practice/sessions` — start a student practice session

(Full request/response shapes live in `api-contract.md`.)

## Database structure (summary)
`subjects → chapters → questions`, where each question carries `topic` as a tag field (not a hierarchy level). Separately, `papers` and `practice_sessions` are joined to `questions` via join tables (`paper_questions`, `practice_session_questions`). All `user_id` columns are nullable now, since auth is deferred post-MVP. (Full schema in `db-schema.md`.)

## What's still open
- Exact PDF-parsing tool/approach for syllabus ingestion
- Final hosting confirmation (AWS vs Render)
- Groq-specific prompt tuning trade-offs (to be filled into ADRs as discovered)

## Related documents (if available to the LLM)
- `spec.md` — full project spec
- `api-contract.md` — complete endpoint reference
- `db-schema.md` — complete database schema
- `prompt-library.md` — finalized generation prompts per question type/marks
- `adr.md` — architecture decisions and reasoning
- `test-plan.md` — test cases
- `ui-wireframes.md` — screens and navigation flow

## How to use this context
When asking any LLM for help on this project (writing code, debugging, refining prompts, reviewing a PR), paste this document first so it understands the domain rules (especially the marks-aware answer requirement), the locked tech stack, and the shared data contract — without it, generic suggestions may not fit the state-board-specific requirements this project depends on.
