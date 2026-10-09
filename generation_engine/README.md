# Generation Engine (Module A)

Turns a `(subject, chapter, type, marks, difficulty, count)` request into a batch of validated `Question` objects. No storage, no HTTP — Module B owns both.

## Install & test

```bash
# from the repo root (pytest.ini and the tests live there, not in this folder)
pip install -r requirements.txt
echo "GROQ_API_KEY=your-key-here" > .env     # only needed for real generation
pytest                      # 307 tests, no network required
```

Settings are read from the environment or a `.env` file and defined in `config.py`. The ones you are most
likely to touch: `GROQ_API_KEY`, `GROQ_MODEL` (default `openai/gpt-oss-120b`), `GROQ_MAX_RETRIES` (3),
`GROQ_TPM_LIMIT` (8000), `MAX_REGENERATION_RETRIES` (2), `NEAR_DUPLICATE_SIMILARITY_THRESHOLD` (0.90),
`MAX_BATCH_COUNT` (25), `REQUIRE_SYLLABUS`, `REQUIRE_TEXTBOOK`, `ENABLE_ANSWER_RULE_CHECKS`,
`ENABLE_LLM_ANSWER_VERIFICATION`, `VERIFIER_MODEL`.

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
| Long | 3 | exactly 3 distinct points/steps |
| Long | 5 | ≥3 structured points, 40+ words, exam-response depth |
| Fill | 1 | a question with one or more `___` blanks; the answer is the word or phrase for the blank |
| Match | 3 or 5 | exactly as many pairs as marks; Column A in `text`, Column B in `options`, key like `1-C, 2-A, 3-B`; items distinct and short, no explanation |

`supported_combinations()` in `prompts.py` lists these (it is what the backend's `GET /generation/combinations`
returns), and `VALID_MARKS_BY_TYPE` in `schemas.py` holds the marks allowed per type. The 1-mark **Short** case is the non-MCQ
1-mark row of spec.md Section 7 ("What is the SI unit of force?" → *Newton*). For Match, the model returns an ordered
list of `{"left", "right"}` pairs and the engine builds the question text, options and key from it, so the key can't
disagree with the columns.

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
| Field-level contract, valid marks per type | `schemas.py` |
| Validation checks (marks format, duplicates, relevance, grounding, board scope, figures) | `validation.py` |
| Answer-key checks | `rule_checks.py` (exact rules), `answer_verification.py` (independent AI pass) |
| Textbook ingestion and passage selection | `textbook_ingest.py`, `textbook.py` |
| Syllabus loading and chapter/grade checks | `syllabus.py`, `syllabus_ingest.py` |
| Difficulty handling | `difficulty.py` |
| Retry/timeout/threshold config | `.env` (see `config.py`) |

Subject rules deliberately live in one registry. Previously the prompt asked for one thing and the validator checked another, and the two drifted apart — which is how correctly-formatted 3-mark answers ended up being rejected.

## Syllabus ingestion

`scripts/ingest_syllabus.py` extracts chapter titles from a textbook PDF's
table of contents and merges them into `backend/data/syllabus.json`. Regex
line-parsing over `pypdf` text extraction, not layout/ML/OCR — see
`syllabus_ingest.py`'s module docstring for why. Always dry-run first
(the default) and review the extracted list before `--write`; contents
pages aren't uniform enough to trust blindly.

```bash
# Find the real contents page first — point this at a generous guess
python scripts/ingest_syllabus.py textbook.pdf --subject Science --pages 1-10

# Narrow down once you've found it, then write for real
python scripts/ingest_syllabus.py textbook.pdf --subject Science --pages 4-5 --write
```

`backend/data/syllabus.json` currently holds a hand-transcribed, per-grade chapter list
(see `backend/data/README.md`) rather than output from this pipeline, since no textbook
PDFs have been run through it yet — re-run the CLI against them when you have them, with
`--mode replace` to swap a subject's list out entirely.

## Still open

- **Factual correctness.** `check_answer_relevance` catches only structurally broken answers. Wrong answer keys are caught by `rule_checks.py` (exact checks for Maths/Science patterns) and `answer_verification.py` (an independent second AI pass, run on demand through `GenerationEngine.verify_answers`, not during `generate()`; see docs/api-contract.md, *Answer verification*). The AI pass is a second opinion from a model, not a proof, and the rules cover only the patterns they recognise, so the manual spot-check in test-plan.md Section 4 still stands. `GenerationEngine.verify_relevance_llm` (off by default, `ENABLE_LLM_RELEVANCE_CHECK=true`) is a separate coherence check.
- **Threshold tuning.** Near-duplicate similarity (0.90) and the word-count bounds are first estimates, not calibrated against real Groq output.

## Figure-based questions

`GenerationRequest.figures` takes up to 20 `FigureContext` objects: a **text description** of a stored diagram
(caption, topic, labelled parts), never the image. The prompt lists them as `F1`, `F2`, ..., the model names the figure a
question is about by that short reference, and the engine attaches the real `figure_id` itself, so the model can't invent
or mis-copy one. Questions that contradict the figure's metadata are dropped and retried (counted in the report as
`dropped_figure_invalid`), and the answer-key verifier sees the same description. Figure requests are written from the
metadata and skip textbook grounding. The backend decides which figures to offer; see `backend/README.md`.

## Answer verification

`GenerationEngine.verify_answers(questions)` runs on demand, not inside `generate()`: `rule_checks.py` applies exact
checks for Maths/Science patterns first, then `answer_verification.py` makes an independent AI pass in chunks (MCQs are
solved blind and compared with the key; Match keys are checked pair by pair). Each question gets
`verification_status` (`verified`, `unverified` or `flagged`) and `verification_note`. Toggles:
`ENABLE_ANSWER_RULE_CHECKS`, `ENABLE_LLM_ANSWER_VERIFICATION`, `VERIFIER_MODEL`, `VERIFICATION_CHUNK_SIZE`.

## Textbook-grounded generation (Karnataka State Board only)

Questions are written **from the KTBS textbook text**, and the chapter list is
**read from the textbook, not hardcoded**.

```
KTBS PDFs --scripts/ingest_textbooks.py--> backend/data/textbooks/*.json
                                              |  (chapters, sections, passages)
                       +----------------------+----------------------+
                       v                                             v
        syllabus = chapters per (subject, grade)        passages the model writes from
```

1. **Ingest** (`generation_engine/textbook_ingest.py`, CLI `scripts/ingest_textbooks.py`):
   finds chapters (explicit list -> PDF outline -> contents page -> "Chapter N"
   headings), splits each into sections and ~900-char passages. Text-layer PDFs
   only (no OCR). Chapters it cannot locate are reported, never invented.
2. **Syllabus**: `TextbookCorpus.to_syllabus_dict()` -> `SyllabusIndex`. A chapter
   is valid only for the grade whose textbook contains it; section titles become
   the chapter's topics.
3. **Coverage**: each batch is assigned `count` passages by `select_passages`
   (coprime-stride walk from `coverage_offset`), so one batch is spread over the
   chapter and repeated batches visit every passage before repeating. The backend
   passes the number of questions already stored for the chapter as the offset.
4. **Prompt**: passages are numbered `[P1]..[Pn]`; exactly one question per
   passage, answerable from that passage alone; the model reports `passage`.
5. **Validation**: `check_grounding` drops questions whose key terms aren't in
   their passage (lexical, stem-level, Kannada-aware); `check_board_scope` drops
   mentions of other boards. Accepted questions carry a `src:<passage-id>` tag and
   a `topic` defaulting to the passage's section.
6. `REQUIRE_TEXTBOOK=true` refuses any (subject, grade, chapter) with no ingested
   textbook text (HTTP 400) instead of letting the model free-write.

Limits: grounding is lexical — it catches off-textbook drift, not a wrong fact
(the manual spot-check in test-plan.md still applies). Kannada needs a Unicode
text layer; legacy-font PDFs extract as garbage and the ingest report says so.
