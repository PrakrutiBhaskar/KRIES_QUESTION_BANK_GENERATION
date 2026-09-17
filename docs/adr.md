# Architecture Decision Records — Question Bank Generator

Short records of key technical decisions and why they were made. Useful for onboarding, code review context, and explaining choices during evaluation/viva.

---

## ADR 1: React Native for both Web and Android
**Decision:** Use a single React Native codebase to target both web and Android, instead of separate frontends.
**Reasoning:** Reduces duplicated frontend work across a 3-person team and keeps the UI consistent between platforms.
**Trade-offs:** Some platform-specific behavior (e.g. PDF download/share) needs separate handling behind a shared interface.

## ADR 2: Groq as the LLM API
**Decision:** Use Groq for question generation.
**Reasoning:** [fill in: cost, speed, or model availability reasoning specific to your team's evaluation]
**Trade-offs:** [fill in once known — e.g. model quality vs. cost vs. latency compared to alternatives]

## ADR 3: FastAPI backend
**Decision:** Use Python/FastAPI for the backend.
**Reasoning:** Team skillset fit; FastAPI's async support suits LLM API calls well; strong typing via Pydantic pairs naturally with the shared `Question` schema.
**Trade-offs:** N/A — team preference-driven decision.

## ADR 4: PostgreSQL as the database
**Decision:** Use PostgreSQL over MongoDB.
**Reasoning:** Data is fundamentally relational (subjects → chapters → topics → questions, plus papers/practice sessions as join tables), which fits a relational DB better than a document store.
**Trade-offs:** Slightly more schema rigidity than MongoDB, but this suits a well-defined question schema.

## ADR 5: No auth in MVP
**Decision:** Ship without login/accounts for MVP; add post-MVP.
**Reasoning:** Reduces MVP scope/complexity; core value (generation + paper building + practice) doesn't require identity.
**Trade-offs:** No saved history/personalization until auth is added. Schema includes nullable `user_id` columns to avoid a rewrite later.

## ADR 6: Marks-aware answer generation
**Decision:** Answer depth/format is explicitly tied to the marks allotted per question, with subject-specific structure (see prompt-library.md).
**Reasoning:** Matches real Karnataka State Board exam expectations — a 1-mark and 5-mark answer should look meaningfully different, not just longer.
**Trade-offs:** Requires more prompt engineering and validation per (subject, marks) combination rather than one generic prompt.

## ADR 7: Syllabus data via PDF parsing
**Decision:** Source chapter/topic structure by parsing official textbook PDFs rather than manual entry.
**Reasoning:** Scales across 5 subjects × 3 grades without manual data entry for every chapter.
**Trade-offs:** Parsing quality varies by PDF structure; some manual cleanup likely needed. [fill in specific tooling once chosen]

## ADR 8: Soft-delete questions instead of hard delete
**Decision:** `DELETE /questions/{id}` sets `is_active = false`; the row stays.
**Reasoning:** Questions are referenced by `paper_questions` and `practice_session_questions`. A hard delete would either break those papers or need a cascade that silently rewrites a teacher's finished paper.
**Trade-offs:** The table grows with discarded rows, and every read path must filter on `is_active`. A periodic purge of rows referenced by nothing can be added later.

## ADR 9: Cache generation by reusing stored questions
**Decision:** A repeated `/generate` with the same (subject, chapter, type, grade, marks, difficulty) is served from stored questions; only the shortfall goes to Groq. `{"refresh": true}` forces fresh generation.
**Reasoning:** spec.md Module B asks for both "avoid regenerating identical requests" and "store generated questions for reuse" — one mechanism satisfies both, with no separate cache table to invalidate.
**Trade-offs:** The cache never expires, so a prompt improvement won't reach users who hit a cached combination until they send `refresh`. The `generation_requests` log table in db-schema.md's design notes is still unbuilt; add it if we want hit-rate metrics.

## ADR 10: Two PDF backends, WeasyPrint preferred
**Decision:** Render via WeasyPrint when available, falling back to ReportLab.
**Reasoning:** Kannada script needs glyph reordering and ligature substitution. WeasyPrint gets that from Pango/HarfBuzz; ReportLab does not, and its built-in fonts have no Kannada glyphs at all. But WeasyPrint needs system libraries that a bare Render container lacks, and a backend that won't boot is worse than one that renders English-only.
**Trade-offs:** Two rendering paths to maintain. The ReportLab path refuses Kannada papers with a 503 rather than emitting empty boxes, so the limitation is explicit rather than silent.

## ADR 11: Malformed requests are 400, not FastAPI's default 422
**Decision:** Request-body validation errors return 400; 422 is reserved for generated output that failed validation.
**Reasoning:** api-contract.md assigns those two codes distinct meanings on `POST /generate`. Leaving FastAPI's default in place would make "you sent bad JSON" and "the model produced an unusable answer" indistinguishable to the frontend.
**Trade-offs:** Diverges from FastAPI convention, so it needs stating in the API docs — done in backend/README.md.

---

*Add new ADRs as decisions are made — keep each one short: decision, reasoning, trade-offs.*
