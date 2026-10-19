# API Contract — Question Bank Generator

Backend: **Python/FastAPI** · Database: **PostgreSQL** · LLM: **Groq**

All endpoints return JSON. Base path: `/api/v1`

## Shared object: Question

```json
{
  "id": "uuid",
  "subject": "Math | Science | Social Science | English | Kannada",
  "chapter": "string",
  "type": "MCQ | Short | Long | Fill | Match",
  "grade": 8,
  "text": "string",
  "options": ["string"],
  "answer": "string",
  "explanation": "string",
  "marks": 1,
  "difficulty": "easy | medium | hard",
  "topic": "string",
  "tags": ["string"],
  "verification_status": "verified | unverified | flagged",
  "verification_note": "string | null"
}
```

`verification_status` / `verification_note` are additive (older clients can ignore
them) and describe whether the answer key has been checked. Generation does not check
it: new questions are `unverified` until someone clicks **Verify answers**
(`POST /questions/verify`); see [Answer verification](#answer-verification).

**Optional extension — figures.** A question that has a diagram attached also carries
`figure` (printed with the question) and/or `answer_figure` (printed only in the answer
key). Both keys are **omitted** when there is no figure, so clients that don't know about
figures see exactly the object above.

```json
"figure": { "id": "uuid", "caption": "string", "mime": "image/png", "width": 900,
            "height": 600, "size_bytes": 48211, "url": "/api/v1/figures/<id>/file" }
```

---

## 1. Generation

### `POST /generate`
Generate a batch of new questions for a subject/chapter.

**Request body**
```json
{
  "subject": "Science",
  "chapter": "Photosynthesis",
  "type": "Short",
  "grade": 8,
  "marks": 3,
  "difficulty": "medium",
  "count": 5
}
```

**Response `200`**
```json
{
  "questions": [ /* array of Question objects */ ]
}
```

**Optional: questions about library figures.** Add `"use_figures": true` to write every
question about a figure from the *shared* figure library (added by administrators) tagged with the request's subject and chapter
(a figure with a `topic` is skipped when the request names a different topic; figures with
no topic count as chapter-wide). Or send `"figure_ids": ["<uuid>", ...]` to name exact
figures (implies `use_figures`; they must exist in the library and have a caption or labels, and need
not be tagged with the chapter). Each returned question then carries its `figure`. At most
`MAX_GENERATION_FIGURES` (default 6) are used per call, the least-used first. The model is
given each figure's caption, topic and labelled parts as text and never sees the image.
Repeat requests are served from stored questions about the same figures only.

Extra errors for figure requests: `400 no_figures` (nothing in the library matches),
`400 figure_has_no_metadata`, `400 too_many_figures`, `404` (unknown figure).

**Errors**
- `400` — invalid subject/chapter/type/grade/marks combination
- `502` — Groq API call failed
- `422` — generated output failed validation (schema mismatch, marks/answer length mismatch)

---

## 2. Retrieval

### `GET /questions`
Filter/search stored questions.

**Query params:** `subject`, `chapter`, `type`, `grade`, `marks`, `difficulty`, `topic`, `search`, `page`, `page_size`

**Response `200`**
```json
{
  "results": [ /* Question objects */ ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

### `GET /questions/{id}`
Fetch a single question by ID.

### `PATCH /questions/{id}`
Edit a question (teacher curation): `text`, `options`, `answer`, `explanation`, `marks`,
`difficulty`, `topic` and `tags`. Editing the `text`, `options` or `answer` resets
`verification_status` to `unverified` (with a note), because a hand-edited key has not been
checked; run **Verify answers** again to check it. An MCQ `answer` must be one of the
options. Also attaches or detaches diagrams:
`figure_id` (printed with the question) and `answer_figure_id` (answer key only) take the
id of any figure in the library, or `null` to detach. Omit a field to leave it unchanged.
Also sets the answer key's **marks split**: `marks_split` is a list of `{"name", "marks"}`
(at most 6 parts, distinct names, each part at least 1 mark) that must add up to the question's
marks, e.g. `[{"name": "Diagram", "marks": 2}, {"name": "Explanation", "marks": 3}]`. It applies
to short and long answers worth more than 1 mark. `null` goes back to the automatic split.
Changing a question's `marks` drops a split that no longer adds up. A question with its own
split returns it as `marks_split` (the key is absent otherwise); every export prints it
instead of the automatic one, as long as it still adds up to the marks the paper gives the
question. Changing the split does not reset `verification_status`.
Teachers and administrators only (`403 editor_required` for a student).
Errors: `403` for a student or for someone else's question, `404` for an unknown figure.

### `GET /questions/{id}/marks-split`
For the marks-split editor: `{marks, marks_split, auto_marks_split, editable}`. `marks_split` is
the teacher's own split (or `null`), `auto_marks_split` is what the key prints automatically,
`editable` is `false` for MCQ, fill-in, match and 1-mark questions. Teachers and administrators only.

### `POST /questions`
Add a question you wrote yourself (`201`, returns the question). Body: `subject`, `chapter`,
`type`, `grade`, `text`, `options` (MCQ), `answer`, `explanation`, `marks`, `difficulty`,
optional `topic`. It gets the same checks as a generated question (shape for its type, marks
allowed for the type, answer length for the marks) and is stored `unverified`, owned by the
caller. `400` for a question that fails a check, `403 editor_required` for a student account.

### `POST /questions/{id}/copy`
Make an editable copy of any question, owned by the caller (`201`, returns the new question).
Only a question's creator may `PATCH` it, so anyone else edits their own copy; the original
is unchanged. The copy can then replace the original in a paper with `PATCH /papers/{id}`
(a question item may carry `section`, used only when the question is newly added).

### `DELETE /questions/{id}`
Discard a question. Teachers and administrators only.

### `POST /questions/verify`
Check the answer keys of stored questions (the **Verify answers** button on the
generation screen). Body: `{"question_ids": ["uuid", ...]}` (1 to 50 ids). Any
signed-in user may verify any stored question.

Response `200`:
```json
{
  "questions": [ /* Question objects, same order as requested, with verification_status / verification_note updated */ ],
  "verified": 0,
  "unverified": 0,
  "flagged": 0
}
```
The result is saved on each question. Re-verifying overwrites the earlier result. A
stored question that is not in a checkable shape reads `unverified` rather than failing
the call. Errors: `404` if an id does not exist, `400`/`422` for an empty or oversized list.

---

## 3. Papers (teacher paper builder)

### `POST /papers`
Create a new paper from selected question IDs.

**Request body**
```json
{
  "title": "Science Unit Test - Chapter 3",
  "subject": "Science",
  "question_ids": ["uuid", "uuid"],
  "total_marks": 20
}
```

**Response `201`** — returns the created paper object with ordered questions.

### `GET /papers/{id}`
Fetch a paper.

### `PATCH /papers/{id}`
Reorder questions / update marks / update title. Teachers and administrators only
(`403 editor_required` for a student, who can still build, read and export their own papers).

---

### Blueprint papers for a whole subject
`POST /papers/blueprint`, `/papers/blueprint/preview` and `/papers/blueprint/jobs` take up to 60
`chapters` (each `{name, weightage}`, weightage adding up to 100), enough to cover every chapter
of a subject in one grade. List them all with even weightage to build a paper for the entire
subject. The paper is still limited to 100 questions, and a chapter can only get a question if
there are at least as many questions as chapters (the preview shows `planned_questions` per
chapter, so a chapter left at 0 is visible before anything is generated).

## 4. Export

### `POST /export/{paper_id}`
Compile a paper into a downloadable PDF.

**Response `200`**
```json
{
  "download_url": "string"
}
```

---

## 5. Practice mode (student)

### `POST /practice/sessions`
Start a practice session for a subject/chapter.

**Request body**
```json
{
  "subject": "Math",
  "chapter": "Algebra",
  "type": "MCQ",
  "grade": 7,
  "difficulty": "easy",
  "count": 10
}
```

**Response `201`** — returns a session with a question set (answers withheld until reveal).

### `GET /practice/sessions/{id}/reveal/{question_id}`
Reveal the answer + explanation for one question in a session. Includes `answer_figure`
when the question has one; before the reveal a student only ever sees `figure`.

---

## 5b. Figures (diagrams)

Not in the original contract. All routes need the bearer token.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/figures` | **Administrators only**: `403 admin_required` for any other role (an admin is made with `scripts/make_admin.py`; the role can't be chosen at sign-up). `multipart/form-data`: `file` (PNG/JPEG; GIF/WebP are converted) and optional `caption` (≤ 300 chars), `subject`, `chapter`, `topic`, `labels` (one per line, or a JSON array; e.g. `A: nucleus`). `201` → figure object. `400 invalid_subject` for an unknown subject. `400 invalid_image` if it isn't a readable image (SVG is refused), `413 payload_too_large` over `MAX_FIGURE_BYTES` (default 5 MB) |
| `GET` | `/figures` | The shared library, newest first (`page`, `page_size`; optional `subject`, `chapter` filters) |
| `GET` | `/figures/{id}` | Metadata. Any signed-in user can read any figure (they travel with shared questions) |
| `GET` | `/figures/{id}/file` | The image bytes. Needs the header, so a browser app fetches it and shows an object URL |
| `PATCH` | `/figures/{id}` | Any of `caption`, `subject`, `chapter`, `topic`, `labels`; only what you send changes, an empty value clears it. **Administrators only** (`403 admin_required`). `400` for a bad value (nothing is changed) |
| `DELETE` | `/figures/{id}` | **Administrators only** (`403 admin_required`). `409 figure_in_use` while a live question still uses it |

**Metadata and privacy.** `subject`, `chapter`, `topic` and `labels` are what question
generation writes from. Figure responses on the figure routes include them only for the
administrators and teachers; for students they come back empty/null. They are never part of the
`figure` object on a question: the labels are effectively an answer key, so they must not
reach practice-mode students.

Uploads are re-encoded server-side: transparency is flattened onto white, EXIF/GPS metadata
is dropped, and the longest side is capped at 2400 px. Attach with `PATCH /questions/{id}`.

In the exported PDF the question's `figure` is printed under the question text and its
`answer_figure` under its entry in the answer key. An answer-key figure also counts as the
"Diagram" part of the marks split.

---

## 6. Syllabus/reference data

### `GET /subjects`
List subjects.

### `GET /syllabus/seeded`
Chapters added from the Syllabus page, optionally filtered by `subject` and `grade` (7-9). Each
has `{id, subject, grade, name, topics, created_by, can_remove}`; `can_remove` is true for the
teacher who added it and for administrators. Teachers and administrators only (`403 editor_required`).

### `POST /syllabus/seed`
Body: `{"subject", "grade": 7-9, "chapters": [{"name", "topics": []}]}` (1-100 chapters; topics
optional). Adds the chapters to the live syllabus for that grade, so they can be generated from
at once (the index is rebuilt and handed to the engine; no restart). Chapters the grade already
has, and repeats within the request, are skipped. Textbook and `syllabus.json` chapters are never
changed. Returns `201 {added: [...], skipped: [names], warning}`; `warning` is set only when no
syllabus was loaded before, because generation then accepts just the seeded chapters. Persisted in
`seeded_chapters` (migration 0011) and merged back in at startup. Teachers and administrators only.

### `DELETE /syllabus/seeded/{id}`
Remove a seeded chapter: `204`. Only its creator or an administrator (`403`); `404` if it is
gone. Questions already generated for it are kept; the chapter is simply no longer offered.

### `GET /subjects/{subject}/chapters`
List chapters for a subject.

---

## Auth note
No auth in MVP — all endpoints are open. When auth is added post-MVP, expect:
- `Authorization: Bearer <token>` header on all endpoints
- `user_id` scoping added to `/papers` and `/practice/sessions`

## Error format (all endpoints)
```json
{
  "error": "string",
  "detail": "string"
}
```

---

## Implementation notes (Module B)

The backend in `/backend` implements everything above. Differences and
additions the frontend should know about — all backwards-compatible:

**Error codes on `POST /generate`.** A malformed request body returns `400`,
not FastAPI's default `422`. `422` means only what this contract says it
means: the *generated output* failed validation. One error parser handles
every endpoint, since all errors use the `{error, detail}` shape above.

**`POST /generate` extra request field.**

| Field | Type | Default | Meaning |
|---|---|---|---|
| `refresh` | bool | `false` | Skip the cache and call Groq for the full count |

By default a repeated identical request is served from stored questions
instead of regenerating. Send `"refresh": true` for a "generate more" action.

**Student accounts.** `POST /generate`, `POST /papers/blueprint` and
`POST /papers/blueprint/jobs` are open to students, database first: stored
questions are served before the model is asked for anything, only the shortfall
is generated, and `refresh` is ignored. The new questions a student may create
are capped per request and per UTC day (`STUDENT_MAX_NEW_QUESTIONS_PER_REQUEST`,
`STUDENT_MAX_NEW_QUESTIONS_PER_DAY`); a request that would exceed the allowance
returns `429 generation_allowance_used` and stores nothing (a paper is refused
before any model call). `POST /questions/verify` stays teacher/admin only
(`403 generation_disabled_for_students` for a student).

**`POST /generate` extra response fields.**

```json
{
  "questions": [ /* Question objects */ ],
  "cached": 2,        // how many came from storage
  "generated": 3,     // how many were newly generated
  "report": { }       // Module A's diagnostic counters, or null on a full cache hit
}
```

**`GET /questions` params.** `page` defaults to 1, `page_size` to 20 (max 100).
Discarded questions are excluded from every listing.

**`POST /papers`.** `total_marks` is optional and server-computed from the
selected questions. If you send a value that disagrees with the computed
total, you get a `400` rather than a silent overwrite. All questions must
belong to the paper's `subject`.

**`PATCH /papers/{id}`.**

```json
{
  "title": "optional new title",
  "questions": [
    {"question_id": "uuid", "order_index": 0, "marks_override": 5}
  ]
}
```

`questions`, when present, **replaces** the whole list — send the full
ordered set currently displayed. Anything omitted is removed from the paper.
`order_index` values are renumbered densely from 0, so a drag-and-drop UI can
send whatever indexes it has. `total_marks` is recalculated.

**`POST /export/{paper_id}`** also returns `filename` and `size_bytes`
alongside `download_url`. The URL points at `GET /export/files/{filename}`.

**Practice sessions.** Questions in a session response carry no `answer` or
`explanation` field at all, plus a `revealed` boolean. Only the reveal
endpoint returns an answer, and only for a question in that session.

**Four endpoints added beyond this contract:**

| Method | Path | Why |
|---|---|---|
| `GET` | `/papers` | The paper-list screen needs it |
| `DELETE` | `/papers/{id}` | Deleting a saved question bank. Returns `204`; the paper's questions stay in the question pool |
| `GET` | `/practice/sessions/{id}` | So a student can resume rather than restart |
| `GET` | `/generation/combinations` | Lets the generation-request screen build its type/marks selectors from the same rule `POST /generate` actually enforces (`generation_engine.prompts.supported_combinations()`), instead of a hardcoded copy that can drift out of sync. Returns e.g. `[{"type": "MCQ", "marks": [1]}, {"type": "Short", "marks": [1, 2, 3]}, {"type": "Long", "marks": [5]}]`. |

**`GET /subjects`** always returns all five subjects, even before any
questions exist, so the picker is never empty. `GET /subjects/{subject}/chapters`
can legitimately return `[]` until chapters are seeded or generated.

---

## Authentication

Bearer-token auth. Errors use the standard `{"error", "detail"}` shape.

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/auth/signup` | `{name, email, password, role?}` (`role`: `Teacher` \| `Student`, default `Teacher`; password ≥ 8 chars with a letter and a number) | `201` `{access_token, token_type: "bearer", expires_in, user}` | `400 invalid_request`, `409 email_taken` |
| POST | `/auth/login` | `{email, password}` | `200` same as sign-up | `401 invalid_credentials` |
| GET | `/auth/me` | none (header `Authorization: Bearer <token>`) | `200` `{id, name, email, role}` | `401 not_authenticated` / `invalid_token` |

`user` is `{id, name, email, role}`. Set `JWT_SECRET` in production.

### Access and ownership

Every endpoint except `POST /auth/signup`, `POST /auth/login`, `GET /health` and
`GET /export/files/{filename}` needs `Authorization: Bearer <token>`; without
one the response is `401 not_authenticated`, and an expired or invalid token is
`401 invalid_token`.

| Resource | Who can do what |
|---|---|
| **Papers** (`/papers`, `POST /export/{id}`) | Owner only. The owner is the signed-in user, taken from the token; sending `user_id` in a request body is a `400`. Someone else's paper is a `404`, identical to a paper that doesn't exist. `GET /papers` lists only your own. |
| **Practice sessions** (`/practice/...`) | Owner only, same `404` rule. |
| **Questions** (`GET /questions`, `GET /questions/{id}`) | Shared pool: any signed-in user can read and reuse stored questions (this is what the generation cache is for). |
| `POST /syllabus/seed`, `GET /syllabus/seeded`, `DELETE /syllabus/seeded/{id}` | Teachers and administrators only (`403 editor_required`); removal further limited to the creator or an administrator. |
| **Every edit** (`PATCH`/`DELETE`/`POST .../copy` on questions, `POST /questions`, `GET /questions/{id}/marks-split`, `PATCH /papers/{id}`) | Teachers and administrators only. A student gets `403 editor_required`. Students can still generate, build papers, export and practise. |
| `PATCH /questions/{id}` | Only the user who generated the question (and only a teacher or administrator); anyone else gets `403 forbidden`. |
| `DELETE /questions/{id}` | Only the creator removes it from the pool. For anyone else it returns `204` and changes nothing, so a teacher can drop a cached question from their own draft without affecting others. |
| **PDF download** (`GET /export/files/{filename}?token=...`) | A browser tab can't send an Authorization header, so `POST /export/{id}` returns a `download_url` carrying a signed token valid for 10 minutes for that one file. No, invalid or expired token: `401 invalid_download_token`. |

Papers, practice sessions and questions created before sign-in existed have no
owner: papers and sessions stay hidden, and questions can't be edited or removed.
Assign them to an account with (replace the email):

```sql
UPDATE papers            SET user_id    = (SELECT id FROM users WHERE email = 'you@example.com') WHERE user_id IS NULL;
UPDATE practice_sessions SET user_id    = (SELECT id FROM users WHERE email = 'you@example.com') WHERE user_id IS NULL;
UPDATE questions         SET created_by = (SELECT id FROM users WHERE email = 'you@example.com') WHERE created_by IS NULL;
```

### Rate limiting

Exceeding a limit returns `429` with `{"error": "rate_limited", "detail": "Too many requests. Try again in N seconds."}`
and a `Retry-After: N` header.

| Bucket | Applies to | Default | Counted per |
|---|---|---|---|
| `global` | every request except `/health` | 120 / min | signed-in user, else IP |
| `login` | `POST /auth/login` | 10 / min | IP |
| `signup` | `POST /auth/signup` | 5 / hour | IP |
| `generate` | `POST /generate`, `POST /questions/verify`, `POST /practice/sessions` | 30 / min | user |
| `export` | `POST /export/{id}` | 10 / min | user |
| failed logins | wrong password | 5 per 15 min, then locked out for the rest of the window | IP + email |

All are configurable (`RATE_LIMIT_*`, `LOGIN_MAX_FAILURES`; see `backend/.env.example`).
Counters are in-process memory, so they reset on restart and are per worker; move
them to Redis before running more than one worker or instance.

---

## Answer verification

The model that writes a question also writes its answer key, so a key can be checked
on request. This is a separate step, not part of generation: `POST /generate` returns
questions as `unverified`, and the **Verify answers** button (`POST /questions/verify`)
checks the ones on screen. Two layers, cheapest first
(`generation_engine/rule_checks.py`, `generation_engine/answer_verification.py`):

1. **Rule checks** (Maths and Science, no LLM): arithmetic, `x%` of `n`, roots and
   powers, LCM/HCF, averages, one-variable linear equations, simple interest,
   area/perimeter/volume of common shapes; SI units, element symbols and atomic
   numbers, common chemical formulas, a few constants, and one-step physics formulas
   (speed, density, force, work, power, pressure, Ohm's law, with unit conversion).
   They only fire when the question matches strictly enough that the answer is
   unambiguous; anything else is left to layer 2.
2. **Independent AI pass** (all subjects, one Groq call per chunk of questions, only when verifying). For MCQs the
   verifier is *not shown* the key: it solves the question itself and its choice is
   compared with the key. For Short/Long/Fill answers it is shown the answer and asked to
   check it sceptically. For Match it is shown the answer and Column B and checks each
   pair on its own; the arithmetic/science rule checks skip Match. Questions a rule already decided are not sent.

| `verification_status` | Meaning | What happens |
|---|---|---|
| `verified` | A rule confirmed the key, or the AI pass reached the same answer | Returned and cached as normal |
| `unverified` | Nothing could be checked: no rule applies, the AI pass wasn't confident, or the call failed | Returned and cached; the key is simply unconfirmed. Questions stored before this feature read as `unverified` |
| `flagged` | A rule or the AI pass found the key wrong | Shown **clearly marked** so the teacher can regenerate or delete it; never served from the cache or used in practice sessions |

Nothing is regenerated automatically: a flagged question stays where it is until the
teacher acts on it. The AI pass fails open: a Groq error leaves questions `unverified`.
Verification never runs during `POST /generate`, so generation does not wait for it and
its `report` carries no verification counters.

Settings (`backend/.env`): `ENABLE_ANSWER_RULE_CHECKS` (default true),
`ENABLE_LLM_ANSWER_VERIFICATION` (default true; set false to skip the AI pass when verifying),
`VERIFIER_MODEL` (optional different model for the second opinion),
`VERIFICATION_CHUNK_SIZE` (default 10). Database: `questions.verification_status` and
`questions.verification_note` (nullable); added automatically with
`AUTO_CREATE_TABLES=true`, or by Alembic migration `0007`.
