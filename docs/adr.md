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

---

*Add new ADRs as decisions are made — keep each one short: decision, reasoning, trade-offs.*
