# Question Bank Generator — Project Spec

**How to use this doc:** Section 1–2 are shared context everyone should read. Section 5 breaks the system into three owned modules (Generation Engine, Backend, Frontend) — each owner should use their subsection as the starting point for their own detailed design doc (API contracts, schemas, screen flows, etc.), then link that doc back here. Sections 6–9 are shared reference material (tech stack, marking scheme, open decisions, sprint plan).

---

## 1. Overview

An AI-powered question bank generator for the **Karnataka State Board, grades 7–9**, covering all core subjects. Teachers can generate and curate chapter-wise question papers; students can generate practice questions for self-study. Questions are generated on demand via the Groq API, complete with answer keys and difficulty tagging.

## 2. Scope (locked decisions)

| Area | Decision |
|---|---|
| Board / Grades | Karnataka State Board, grades 7–9 |
| Subjects | Math, Science, Social Science, English, Kannada |
| Question types | MCQ, Short answer, Long answer |
| Generation method | Groq (LLM API) |
| Platforms | Web + Android, shared codebase via React Native |
| Users | Teachers (paper building) and Students (practice) |
| Auth | Not in MVP — add post-MVP |
| Syllabus data source | Parsed from textbook PDFs |
| Hosting | AWS/cloud platform preferred; Render as fallback |
| MVP scope | Full app — generation, paper builder, practice mode, export |

## 3. User roles & core flows

**Teacher flow:**
1. Select subject → chapter(s)
2. Choose question types, counts, and difficulty mix
3. Generate → review/edit/discard questions
4. Assemble into a paper (reorder, assign marks)
5. Export as PDF

**Student flow:**
1. Select subject → chapter
2. Choose question type/difficulty
3. Generate a practice set
4. Attempt questions, reveal answers/explanations
5. (Optional) Track progress over chapters

## 4. Shared data contract

Everything below is built around one shared question object — all three modules should treat this as the source of truth:

```
Question {
  id
  subject        // Math | Science | Social Science | English | Kannada
  chapter
  type           // MCQ | Short | Long
  grade          // 7 | 8 | 9 — selected per request, not assumed
  text
  options        // only for MCQ
  answer
  explanation
  marks          // 1 | 2 | 3 | 5
  difficulty     // easy | medium | hard
  topic          // tag on the answer key, not part of the syllabus hierarchy
  tags[]
}
```

Syllabus structure: `Subject → Chapter` (topic is a tag on each question's answer key, not a hierarchy level)

---

## 5. Module breakdown (one per owner)

### Module A — Generation Engine
*Owner should expand this into a standalone doc covering: prompt templates per type, exact JSON output schema, validation rules, and test cases per subject.*

- Syllabus data structured as: Subject → Chapter, with `topic` captured as a tag on each generated question rather than a separate hierarchy level
- Prompt templates per question type (MCQ / Short / Long), each returning the shared `Question` JSON shape
- **Marks-aware answer generation:** answer depth/format must match the marks allotted (see Section 7 for the full reference table):
  - 1 mark → direct one-line answer, no explanation
  - 2 marks → brief answer, 1–2 supporting points
  - 3 marks → structured answer, 3 key points/steps
  - 5 marks → detailed multi-point/step answer, exam-response style
  - MCQs → correct option + short justification
- Marks-to-format mapping configurable per subject (Math needs step derivations; Social Science needs distinct points)
- Difficulty tagging (easy/medium/hard) — prompted directly or scored post-generation
- Output validation: schema check, duplicate detection, answer-match verification, marks-vs-answer-length check
- Batch generation: N questions per (subject, chapter, type, marks, difficulty) request
- **Hands off to Backend via:** the Generation API contract (Module B) — agree on this first

### Module B — Backend & Data Layer
*Owner should expand this into a standalone doc covering: full schema/migrations, all API endpoint specs (request/response shape, error handling), and caching strategy.*

- **Schema:** `subjects → chapters → topics → questions`, using the shared `Question` object (Section 4)
- **Generation API:** accepts `{subject, chapter, type, grade, marks, difficulty, count}` → calls Module A's generation logic → validates → stores → returns questions
- **Retrieval API:** filter/search questions by subject/chapter/type/marks/difficulty
- **Export API:** compiles a selected question set into a PDF
- **Auth:** deferred post-MVP — design schema so it can be added without a rewrite (e.g. nullable `user_id` on saved sets)
- **Caching:** avoid regenerating identical requests; store generated questions for reuse
- **Hands off to Frontend via:** the API contract (endpoints, request/response JSON) — agree on this first

### Module C — Frontend (Web + Android, React Native)
*Owner should expand this into a standalone doc covering: screen list with wireframes, navigation flow, and state management approach.*

- Subject/chapter selector
- Generation request screen (type, grade, marks, difficulty, count) with loading state
- Question bank browser: search, filter, edit, discard
- Paper builder (teacher): select, reorder, assign marks, preview
- Practice mode (student): attempt, reveal answer/explanation
- PDF export/download trigger
- Single React Native codebase targeting both web and Android

---

## 6. Tech stack

| Layer | Choice |
|---|---|
| Frontend (Web + Android) | React Native (shared codebase across both platforms) |
| Backend | Node.js/Express or Python/FastAPI (pick based on team's stronger skillset) |
| Database | PostgreSQL / MongoDB |
| LLM API | Groq |
| Syllabus ingestion | PDF parsing of textbook content → structured chapter/topic JSON |
| Export | PDF generation library (e.g. Puppeteer, WeasyPrint, or a PDF component library) |
| Auth | Deferred — not in MVP |
| Hosting | AWS (or another cloud platform) preferred if budget/complexity allows; Render as fallback |

## 7. Mark-scheme reference (for Module A's prompt design)

| Marks | Expected answer format | Example (Science) | Example (Social Science) | Example (Math) |
|---|---|---|---|---|
| 1 | Single word/phrase or one-line fact, no explanation | "What is the SI unit of force?" → *Newton* | "Who was the first President of India?" → *Dr. Rajendra Prasad* | Direct numeric/short answer, no working shown |
| 2 | 1–2 line answer with one supporting reason/point | "Why does ice float on water?" → states the reason (density) in 1–2 lines | "Name two Fundamental Rights." → lists 2 rights, no elaboration | Answer with 1 line of working shown |
| 3 | 3 distinct points, or a short structured explanation (definition + example + 1 extra point) | "Explain photosynthesis." → 3 points: process, inputs/outputs, significance | "Explain any three causes of the 1857 revolt." → 3 distinct causes, 1 line each | 2–3 steps of working shown, final answer |
| 5 | Detailed answer: multiple points/paragraphs, may include diagram reference, example, or derivation; structured like a full exam response | "Describe the human digestive system." → full multi-part answer covering organs, process, and function, diagram reference | "Discuss the causes and effects of the French Revolution." → causes + effects as separate structured sections | Full step-by-step derivation/solution with all intermediate steps shown |

**MCQ answers** (any subject): correct option + 1-line justification — no marks-based scaling needed since MCQs are typically fixed at 1 mark.

**Prompting tip:** give the model explicit structure rather than just the mark value — e.g. "Answer in 3 sections: causes (min 3 points), effects (min 2 points), conclusion (1 line)." This produces far more consistent, exam-ready output than relying on the model to infer structure from marks alone.

## 8. Remaining decisions

Most major decisions are locked. What's left, and who it affects:

| Decision | Affects | Status |
|---|---|---|
| Backend language: Node.js/Express vs Python/FastAPI | Module B | Open — team skillset call |
| Database: PostgreSQL vs MongoDB | Module B | Open |
| PDF-parsing approach for syllabus ingestion (library/tool, manual cleanup needed) | Module A | Open |
| Final hosting confirmation — AWS feasibility vs Render fallback | Module B / DevOps | Open |

## 9. Suggested team split (rotating mini-sprint model)

1. **Sprint 1 (Generation):** all three build generation logic — one per question type (MCQ/Short/Long) — against the shared `Question` contract (Section 4)
2. **Sprint 2 (Backend):** one on schema+storage, one on generation/retrieval API, one on export API
3. **Sprint 3 (Frontend):** one on selector+generation UI, one on question bank browser+paper builder, one on practice mode+export UI

This ensures each person touches every layer and can speak to the full system — and each sprint's owner-of-the-moment should use Section 5's relevant module breakdown as their doc template.
