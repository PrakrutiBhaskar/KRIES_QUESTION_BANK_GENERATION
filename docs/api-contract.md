# API Contract — Question Bank Generator

Backend: **Python/FastAPI** · Database: **PostgreSQL** · LLM: **Groq**

All endpoints return JSON. Base path: `/api/v1`

## Shared object: Question

```json
{
  "id": "uuid",
  "subject": "Math | Science | Social Science | English | Kannada",
  "chapter": "string",
  "type": "MCQ | Short | Long",
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
them) and describe whether the answer key was checked when the question was
generated; see [Answer verification](#answer-verification).

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
Edit a question (teacher curation): `text`, `options`, `explanation`, `marks`, `difficulty`,
`topic` and `tags`. **The `answer` cannot be edited**: any request that includes the field
gets `400` and nothing is changed. The answer key is verified when the question is generated
(see *Answer verification*), so a hand-edited key would carry a verified badge for an answer
nobody checked. To get a different answer, generate the question again. Also attaches or
detaches diagrams:
`figure_id` (printed with the question) and `answer_figure_id` (answer key only) take the
id of any figure in the library, or `null` to detach. Omit a field to leave it unchanged.
Errors: `403` for someone else's question, `404` for an unknown figure.

### `DELETE /questions/{id}`
Discard a question.

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
Reorder questions / update marks / update title.

---

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
| `PATCH /questions/{id}` | Only the user who generated the question; anyone else gets `403 forbidden`. |
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
| `generate` | `POST /generate`, `POST /practice/sessions` | 30 / min | user |
| `export` | `POST /export/{id}` | 10 / min | user |
| failed logins | wrong password | 5 per 15 min, then locked out for the rest of the window | IP + email |

All are configurable (`RATE_LIMIT_*`, `LOGIN_MAX_FAILURES`; see `backend/.env.example`).
Counters are in-process memory, so they reset on restart and are per worker; move
them to Redis before running more than one worker or instance.

---

## Answer verification

The model that writes a question also writes its answer key, so every generated
batch is checked before it is returned. Two layers, cheapest first
(`generation_engine/rule_checks.py`, `generation_engine/answer_verification.py`):

1. **Rule checks** (Maths and Science, no LLM): arithmetic, `x%` of `n`, roots and
   powers, LCM/HCF, averages, one-variable linear equations, simple interest,
   area/perimeter/volume of common shapes; SI units, element symbols and atomic
   numbers, common chemical formulas, a few constants, and one-step physics formulas
   (speed, density, force, work, power, pressure, Ohm's law, with unit conversion).
   They only fire when the question matches strictly enough that the answer is
   unambiguous; anything else is left to layer 2.
2. **Independent AI pass** (all subjects, one extra Groq call per batch). For MCQs the
   verifier is *not shown* the key: it solves the question itself and its choice is
   compared with the key. For Short/Long answers it is shown the answer and asked to
   check it sceptically. Questions a rule already decided are not sent.

| `verification_status` | Meaning | What happens |
|---|---|---|
| `verified` | A rule confirmed the key, or the AI pass reached the same answer | Returned and cached as normal |
| `unverified` | Nothing could be checked: no rule applies, the AI pass wasn't confident, or the call failed | Returned and cached; the key is simply unconfirmed. Questions stored before this feature read as `unverified` |
| `flagged` | A rule or the AI pass found the key wrong, and no replacement could be generated | Returned **clearly marked** so the teacher can review it; never served from the cache or used in practice sessions |

A key found wrong is not returned as-is: the engine drops the question and
regenerates a replacement (telling the model what was wrong), up to the normal retry
limit. Only if that fails does it fill the batch with the `flagged` ones, so a
generation request never fails just because of a strict verifier. The AI pass fails
open: a Groq error leaves questions `unverified`.

`POST /generate` `report` gains `answers_verified`, `answers_unverified`,
`dropped_wrong_answer` (keys found wrong and replaced) and `flagged_kept`.

Settings (`backend/.env`): `ENABLE_ANSWER_RULE_CHECKS` (default true),
`ENABLE_LLM_ANSWER_VERIFICATION` (default true; set false to skip the extra Groq call),
`VERIFIER_MODEL` (optional different model for the second opinion),
`VERIFICATION_CHUNK_SIZE` (default 10). Database: `questions.verification_status` and
`questions.verification_note` (nullable); added automatically with
`AUTO_CREATE_TABLES=true`, or by Alembic migration `0007`.
