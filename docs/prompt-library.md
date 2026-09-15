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
topic "{topic}", difficulty {difficulty}, suitable for a Karnataka State Board
grade 7-9 student.

For each question return:
- question text
- 4 options
- the correct option
- a 1-line justification for the correct answer

Return as a JSON array matching this shape: [...]
```

**Known issues:** (fill in as discovered — e.g. model sometimes returns 3 or 5 options, duplicate distractors, etc.)

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
- **Math:** 5-mark answers need full step-by-step derivations, not just the final answer.
- **Social Science:** 5-mark answers should be split into clearly labeled sections (e.g. causes / effects).
- **Science:** encourage diagram references in explanation text even though no actual diagram is generated.
- **English / Kannada:** short/long answers may need passage-based context — confirm format once syllabus parsing is in place.

## Validation checklist (apply to every generated batch)
- [ ] Output is valid JSON matching the shared `Question` schema
- [ ] No duplicate questions within a batch
- [ ] Answer content actually matches the question asked
- [ ] Answer length/structure matches the assigned marks (see mark-scheme reference in spec.md)
