# Generation Engine (Module A)

Turns a `(subject, chapter, type, marks, difficulty, count)` request into a batch of validated `Question` objects. No storage, no HTTP — Module B owns both.

## Install & test

```bash
pip install -r requirements.txt
cp .env.example .env        # add your GROQ_API_KEY
pytest                      # 100 tests, no network required
```

## Usage

```python
from generation_engine import GenerationEngine, GenerationRequest, Subject, QuestionType, Difficulty

engine = GenerationEngine()

request = GenerationRequest(
    subject=Subject.SCIENCE,
    chapter="Nutrition in Plants",
    type=QuestionType.SHORT,
    marks=3,
    difficulty=Difficulty.MEDIUM,
    count=5,
    topic="Photosynthesis",   # optional narrowing hint
)

questions, report = await engine.generate(request)
```

`generate()` returns a **tuple**. The report is diagnostic — log it, don't return it. See `exceptions.py` for the full FastAPI wiring example.

## Error contract

| Exception | HTTP | Raised when |
|---|---|---|
| `InvalidRequestError` | 400 | bad subject/chapter/type/marks/count combination |
| `GroqAPIError` | 502 | Groq call failed after transport retries |
| `GenerationValidationError` | 422 | couldn't assemble `count` valid questions within the retry budget |

Nothing is ever persisted by this module, so "no partial data stored" holds as long as Module B stores only on success.

## Supported (type, marks) combinations

| Type | Marks | Answer shape |
|---|---|---|
| MCQ | 1 | 4 options, one correct, 1-line justification |
| Short | 1 | single word/phrase, no explanation |
| Short | 2 | 1–2 lines, one supporting point |
| Short | 3 | exactly 3 distinct points/steps |
| Long | 5 | ≥3 structured points, exam-response depth |

The 1-mark **Short** case is the non-MCQ 1-mark row of spec.md Section 7 ("What is the SI unit of force?" → *Newton*).

## How a batch is assembled

1. Request combination check → `InvalidRequestError`
2. Prompt built for the `(type, marks)` pair, with the subject's guidance appended
3. Groq call (retries 429/5xx with exponential backoff)
4. Per-item schema validation → dropped items counted
5. Marks-format + relevance checks → dropped items counted
6. Duplicate check, against items already accepted in earlier attempts too
7. Shortfall triggers another attempt, **with the previous attempt's rejection reasons appended to the prompt** so the model corrects rather than resampling blindly
8. Still short after the retry budget → `GenerationValidationError`

## Where to change things

| Change | File |
|---|---|
| Prompt wording | `prompts.py` (and mirror it into `docs/prompt-library.md`) |
| Marks thresholds, subject rules | `subject_formats.py` — read by prompts *and* validation |
| Field-level contract | `schemas.py` |
| Retry/timeout/threshold config | `.env` (see `config.py`) |

Subject rules deliberately live in one registry. Previously the prompt asked for one thing and the validator checked another, and the two drifted apart — which is how correctly-formatted 3-mark answers ended up being rejected.

## Still open

- **Syllabus ingestion.** `SyllabusIndex.from_json` is the drop-in point; the PDF-parsing tool is still an open decision (spec.md Section 8). Without an index, any non-blank chapter is accepted.
- **Factual correctness.** `check_answer_relevance` catches only structurally broken answers. `GenerationEngine.verify_relevance_llm` adds a second LLM pass for coherence (off by default, `ENABLE_LLM_RELEVANCE_CHECK=true`), but it checks coherence, not truth. The manual spot-check in test-plan.md Section 4 still stands.
- **Threshold tuning.** Near-duplicate similarity (0.90) and the word-count bounds are first estimates, not calibrated against real Groq output.
