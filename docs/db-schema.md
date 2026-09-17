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
| type | enum | `MCQ`, `Short`, `Long` |
| grade | int | 7, 8, or 9 — the grade this specific question was generated for (see `subjects.grade_range` for the subject-wide span; this is per-question) |
| text | text | question text |
| options | jsonb (nullable) | array of strings, MCQ only |
| answer | text | |
| explanation | text | |
| marks | int | 1, 2, 3, or 5 |
| difficulty | enum | `easy`, `medium`, `hard` |
| topic | text | tag describing the sub-topic within the chapter — lives on the answer key, not the syllabus hierarchy |
| tags | text[] | |
| created_at | timestamptz | |

**Indexes:** on `(subject_id, chapter_id, type, grade, marks, difficulty)` for fast filtering.

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
- Consider a `generation_requests` log table later if you want to track/cache LLM calls (subject+chapter+type+marks+difficulty → cached result), but not required for MVP.
