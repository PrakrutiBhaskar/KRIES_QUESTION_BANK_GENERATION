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
  "tags": ["string"]
}
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
Edit a question (teacher curation).

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
Reveal the answer + explanation for one question in a session.

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

**Two endpoints added beyond this contract:**

| Method | Path | Why |
|---|---|---|
| `GET` | `/papers` | The paper-list screen needs it |
| `GET` | `/practice/sessions/{id}` | So a student can resume rather than restart |

**`GET /subjects`** always returns all five subjects, even before any
questions exist, so the picker is never empty. `GET /subjects/{subject}/chapters`
can legitimately return `[]` until chapters are seeded or generated.
