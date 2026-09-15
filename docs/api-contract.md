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
- `400` — invalid subject/chapter/type/marks combination
- `502` — Groq API call failed
- `422` — generated output failed validation (schema mismatch, marks/answer length mismatch)

---

## 2. Retrieval

### `GET /questions`
Filter/search stored questions.

**Query params:** `subject`, `chapter`, `type`, `marks`, `difficulty`, `topic`, `search`, `page`, `page_size`

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
