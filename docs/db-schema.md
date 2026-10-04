# Database Schema — Question Bank Generator

Database: **PostgreSQL**

## Tables

### `subjects`
| Column | Type | Notes |
|---|---|---|
| id | uuid (PK) | |
| name | text | e.g. "Science" |
| grade_range | text | e.g. "7-9" |

### `chapters`
| Column | Type | Notes |
|---|---|---|
| id | uuid (PK) | |
| subject_id | uuid (FK → subjects.id) | |
| name | text | |
| order_index | int | for display ordering |

### `questions`
| Column | Type | Notes |
|---|---|---|
| id | uuid (PK) | |
| subject_id | uuid (FK → subjects.id) | |
| chapter_id | uuid (FK → chapters.id) | |
| type | enum | `MCQ`, `Short`, `Long`, `Fill`, `Match` (the last two added in migration `0009`) |
| grade | int | 7, 8, or 9 — the grade this specific question was generated for (see `subjects.grade_range` for the subject-wide span; this is per-question) |
| text | text | question text |
| options | jsonb (nullable) | array of strings: the 4 choices for MCQ, Column B (one per pair) for Match; null for other types |
| answer | text | |
| explanation | text | |
| marks | int | 1, 2, 3, or 5 |
| difficulty | enum | `easy`, `medium`, `hard` |
| topic | text | tag describing the sub-topic within the chapter — lives on the answer key, not the syllabus hierarchy |
| tags | text[] | |
| figure_id | uuid (nullable, FK → figures.id, ON DELETE SET NULL) | diagram printed with the question |
| answer_figure_id | uuid (nullable, FK → figures.id, ON DELETE SET NULL) | diagram printed only in the answer key |
| created_at | timestamptz | |

**Indexes:** on `(subject_id, chapter_id, type, grade, marks, difficulty)` for fast filtering.

### `figures`
Metadata for an uploaded diagram. The image itself is a file in `FIGURE_DIR` named `filename`.

| Column | Type | Notes |
|---|---|---|
| id | uuid (PK) | |
| owner_id | uuid (nullable) | the administrator who uploaded it (`users.id`); informational. The library is shared: any admin can edit or delete a figure, any user can attach it |
| filename | text (unique) | server-generated `<uuid>.png` / `.jpg`, never the client's name |
| mime | text | `image/png` or `image/jpeg` |
| width, height | int | pixels, after re-encoding |
| size_bytes | int | |
| caption | text | printed under the figure |
| subject | text (nullable) | canonical subject name; with `chapter`, how `use_figures` finds it |
| chapter | text (nullable) | matched case-insensitively |
| topic | text (nullable) | optional sub-topic; empty = whole chapter |
| labels | text[] / json (nullable) | labelled parts, e.g. `["A: nucleus", "B: cell wall"]`; owner-visible only |
| created_at | timestamptz | |

### `papers`
| Column | Type | Notes |
|---|---|---|
| id | uuid (PK) | |
| title | text | |
| subject_id | uuid (FK → subjects.id) | |
| total_marks | int | |
| user_id | uuid (nullable, FK → users.id) | null until auth is added |
| created_at | timestamptz | |

### `paper_questions`
Join table — ordered questions within a paper.

| Column | Type | Notes |
|---|---|---|
| paper_id | uuid (FK → papers.id) | |
| question_id | uuid (FK → questions.id) | |
| order_index | int | |
| marks_override | int (nullable) | if marks differ from question default |

### `practice_sessions`
| Column | Type | Notes |
|---|---|---|
| id | uuid (PK) | |
| subject_id | uuid (FK → subjects.id) | |
| chapter_id | uuid (FK → chapters.id) | |
| user_id | uuid (nullable, FK → users.id) | null until auth is added |
| created_at | timestamptz | |

### `practice_session_questions`
Join table — questions included in a practice session, with reveal state.

| Column | Type | Notes |
|---|---|---|
| session_id | uuid (FK → practice_sessions.id) | |
| question_id | uuid (FK → questions.id) | |
| revealed | boolean | default false |

### `users` (post-MVP, not built for MVP)
| Column | Type | Notes |
|---|---|---|
| id | uuid (PK) | |
| role | enum | `teacher`, `student` |
| name | text | |
| email | text | |
| created_at | timestamptz | |

## Relationships (summary)
```
subjects 1─* chapters
subjects 1─* questions
chapters 1─* questions   (question.topic is a tag field, not a hierarchy level)
papers *─* questions (via paper_questions)
practice_sessions *─* questions (via practice_session_questions)
```

## Design notes
- `user_id` columns are nullable now so auth can be bolted on post-MVP without a schema rewrite.
- `questions.options` uses `jsonb` rather than a separate table — simpler for MCQ's fixed small option set.
- Fill and Match need no extra columns. A Fill question's `text` holds one `_____` blank and `answer` the missing word(s). A Match question keeps Column A as numbered lines in `text` (`1. ...`, `2. ...`), Column B in `options`, and its key in `answer` as `1-C, 2-A, 3-B` (letters index into `options`). One mark per pair, so `marks` is 3 or 5 and `options` has `marks` entries.
- `question_type` is a native PostgreSQL enum; adding a value needs `ALTER TYPE ... ADD VALUE`, done by migration `0009` and by `ensure_schema` at startup. PostgreSQL cannot drop an enum value, so the `0009` downgrade is a no-op.
- Consider a `generation_requests` log table later if you want to track/cache LLM calls (subject+chapter+type+marks+difficulty → cached result), but not required for MVP.
