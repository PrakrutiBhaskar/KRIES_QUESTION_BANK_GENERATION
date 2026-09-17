# Prompt Library — Question Bank Generator

Track finalized prompts here as they're built and tuned. Update this doc whenever a prompt changes — treat it as the source of truth, not the code comments.

## Format for each entry
- **Question type / marks:**
- **Subject-specific?** (yes/no — note variations if yes)
- **Prompt template:**
- **Expected output shape:**
- **Known issues / edge cases:**
- **Last updated:**

---

## MCQ (1 mark)

**Prompt template:**
```
Generate {count} multiple-choice questions for {subject}, chapter "{chapter}",
topic "{topic}", difficulty {difficulty}.

For each question return:
- question text
- 4 options
- the correct option
- a 1-line justification for the correct answer

Return as a JSON array matching this shape: [...]
```

**Grade:** every prompt now carries a `Target grade: Karnataka State Board Class {grade}.` line, appended once in the shared footer (`prompts.py::_footer`) rather than per-template, so it's consistent across all five (type, marks) combinations. `grade` is a required field on `GenerationRequest`/`Question` (`grade: int`, one of `7 | 8 | 9`) — see spec.md Section 4 and api-contract.md.

**Known issues:** model occasionally returns 3 or 5 options, or duplicate distractors — both are rejected by the `Question` schema rather than repaired. `response_format: json_object` is set on the Groq call, which means the array often arrives nested under a key; `GroqClient._parse_json_array` unwraps it.

**Last updated:** engine implementation (see `generation_engine/prompts.py`).

---

## Short answer (1 mark)

**Prompt template:**
```
Generate {count} one-mark questions for {subject}, chapter "{chapter}",
difficulty {difficulty}.

Each answer must be a single word, a short phrase, or one direct factual
line — the kind of answer a 1-mark question is awarded full marks for
(e.g. "What is the SI unit of force?" -> "Newton"). Do NOT explain,
justify, or add working. Leave "explanation" as an empty string.
```

**Known issues:** the non-MCQ 1-mark case is required by spec.md Section 7 (the mark-scheme table gives 1-mark examples for Math, Science and Social Science that are not MCQs). It is generated as `type: Short, marks: 1`. Validation rejects any answer over 15 words, or any answer that carries an explanation.

---

## Short answer (2 marks)

**Prompt template:**
```
Generate {count} short-answer questions for {subject}, chapter "{chapter}",
difficulty {difficulty}. Each answer should be 1-2 lines with one supporting
reason or point, matching how a 2-mark answer would be evaluated on a
Karnataka State Board exam.
```

## Short answer (3 marks)

**Prompt template:**
```
Generate {count} questions for {subject}, chapter "{chapter}", difficulty
{difficulty}. Each answer must contain exactly 3 distinct points or steps,
matching how a 3-mark answer would be evaluated on a Karnataka State Board
exam.
```

## Long answer (5 marks)

**Prompt template:**
```
Generate {count} questions for {subject}, chapter "{chapter}", difficulty
{difficulty}. Each answer must be a detailed, structured response worth full
marks on a Karnataka State Board 5-mark question — include multiple points
or steps, and reference a diagram/example where relevant. Structure the
answer explicitly, e.g.: "Answer in N sections: ..." rather than leaving
structure implicit.
```

---

## Subject-specific notes

These live in code as a single registry — `generation_engine/subject_formats.py`. Both the prompt layer and the validation layer read from it, so a subject's prompt guidance and the rule that checks the model's output cannot drift apart. Edit `SUBJECT_FORMATS` there (or call `register_subject_format` at startup) rather than editing prompts and validators separately.

- **Math:** 5-mark answers need full step-by-step derivations, not just the final answer. Validated by requiring derivation language or working in the answer.
- **Social Science:** 5-mark answers should be split into clearly labeled sections (e.g. causes / effects). The splitter treats `Label:` headings as structure and flattens each section into its sentences when counting points.
- **Science:** encourage diagram references in explanation text even though no actual diagram is generated.
- **English / Kannada:** questions must be self-contained — any passage or sentence the question asks about is included in the question text, since there is no external passage the student can see. Kannada additionally asks for Kannada script and uses relaxed word-count bounds, because whitespace word counts don't map cleanly onto the script. Still to confirm against real syllabus data once PDF parsing lands.

## Where the marks rules live
Numeric thresholds (point counts, word counts, whether an explanation is allowed) are **not** hardcoded in the validators. They live in `DEFAULT_MARKS_RULES` and per-subject overrides in `subject_formats.py`, derived from the mark-scheme reference table in spec.md Section 7.

## Validation checklist (apply to every generated batch)
- [ ] Output is valid JSON matching the shared `Question` schema
- [ ] No duplicate questions within a batch
- [ ] Answer content actually matches the question asked
- [ ] Answer length/structure matches the assigned marks (see mark-scheme reference in spec.md)
