# Test Plan — Question Bank Generator

## 1. Generation engine tests
| Test case | Expected result |
|---|---|
| Generate MCQ, 1 mark | Returns question with exactly 4 options, 1 correct answer, 1-line justification |
| Generate short answer, 2 marks | Answer is 1-2 lines with one supporting point |
| Generate short answer, 3 marks | Answer contains exactly 3 distinct points/steps |
| Generate long answer, 5 marks | Answer contains multiple structured points/sections |
| Generate batch of N questions | Returns exactly N questions, no duplicates within batch |
| Generate for each subject (Math, Science, Social Science, English, Kannada) | Output respects subject-specific answer structure (see prompt-library.md) |
| Malformed/invalid subject or chapter | Returns `400` error, no partial data stored |
| Groq API failure/timeout | Returns `502` error, no partial data stored |
| Generated output fails schema validation | Returns `422`, question is not persisted |

## 2. Backend API tests
| Endpoint | Test cases |
|---|---|
| `POST /generate` | Valid request succeeds; invalid marks/type combination rejected; count limits enforced |
| `GET /questions` | Filters work individually and combined; pagination correct; empty result set handled |
| `PATCH /questions/{id}` | Edits persist; invalid field values rejected |
| `DELETE /questions/{id}` | Question removed; already-deleted ID returns `404` |
| `POST /papers` | Paper created with correct question order and total marks |
| `PATCH /papers/{id}` | Reorder and marks-override persist correctly |
| `POST /export/{paper_id}` | Returns valid downloadable PDF matching paper content |
| `POST /practice/sessions` | Session created with correct question set; answers withheld until reveal |
| `GET /practice/sessions/{id}/reveal/{question_id}` | Returns answer/explanation only for valid session+question pair |

## 3. Frontend tests
- Subject/chapter selector correctly loads syllabus data and updates chapter list per subject
- Generation request screen shows loading state and handles generation errors gracefully
- Question bank browser filters/search return correct subset
- Paper builder: reordering updates persist, total marks recalculates correctly
- Practice mode: reveal shows correct answer for the correct question, doesn't leak other answers
- PDF export/download works on both web and Android targets

## 4. Data/content quality checks (manual spot-check)
- Pull a random sample of generated questions per subject and manually verify:
  - Factual correctness of the answer
  - Answer format matches assigned marks (per mark-scheme reference)
  - No obviously duplicate or near-duplicate questions across a chapter's question bank

## 5. Non-functional
- Generation response time under acceptable threshold (define target, e.g. < 10s for a batch of 10)
- Backend handles concurrent generation requests without data corruption
- PDF export handles papers with a large number of questions without breaking layout
