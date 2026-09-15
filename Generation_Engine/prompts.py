"""
Prompt templates — one function per (type, marks) combination, matching
prompt-library.md. This module is the single place prompts live; keep it in
sync with prompt-library.md whenever a template changes (that doc is the
source of truth for *why* a prompt looks the way it does — this file is the
executable version of it).

Every prompt asks for strict JSON so the response can be parsed directly
against the `Question` schema.
"""
from __future__ import annotations

from .schemas import GenerationRequest, QuestionType, Subject

# ---------------------------------------------------------------------------
# Subject-specific structure notes (project-context.md / prompt-library.md)
# ---------------------------------------------------------------------------

SUBJECT_NOTES: dict[Subject, str] = {
    Subject.MATH: (
        "For 5-mark answers, show the FULL step-by-step derivation, not just "
        "the final answer — number each step. For lower marks, show only as "
        "much working as the mark value implies (1 mark = no working, 2 marks "
        "= 1 line of working, 3 marks = 2-3 steps)."
    ),
    Subject.SOCIAL_SCIENCE: (
        "For 5-mark answers, split the answer into clearly labeled sections "
        "(e.g. 'Causes:' and 'Effects:', or 'Causes:' / 'Consequences:' as "
        "appropriate to the question) rather than one undivided paragraph."
    ),
    Subject.SCIENCE: (
        "Where relevant, reference a diagram or concrete example in the "
        "explanation text (e.g. 'as shown in a labeled diagram of ...'), even "
        "though no actual image is generated."
    ),
    Subject.ENGLISH: (
        "If the question is naturally passage- or grammar-based, keep it "
        "self-contained (include any short passage/sentence needed to answer "
        "it directly in the question text) rather than assuming an external "
        "passage the student can't see."
    ),
    Subject.KANNADA: (
        "If the question is naturally passage- or grammar-based, keep it "
        "self-contained (include any short passage/sentence needed to answer "
        "it directly in the question text) rather than assuming an external "
        "passage the student can't see."
    ),
}

# ---------------------------------------------------------------------------
# JSON output contract shared by every prompt
# ---------------------------------------------------------------------------

_JSON_SHAPE_MCQ = """{
  "text": "string",
  "options": ["string", "string", "string", "string"],
  "answer": "string (must exactly match one of the 4 options)",
  "explanation": "string (1-line justification for the correct answer)",
  "topic": "string (short sub-topic tag within the chapter)",
  "tags": ["string"]
}"""

_JSON_SHAPE_DESCRIPTIVE = """{
  "text": "string",
  "answer": "string",
  "explanation": "string (may repeat/expand on the answer's reasoning; may be empty for 1-mark)",
  "topic": "string (short sub-topic tag within the chapter)",
  "tags": ["string"]
}"""


def _base_system_prompt() -> str:
    return (
        "You are an expert Karnataka State Board question paper setter for "
        "grades 7-9. You write syllabus-aligned exam questions with answer "
        "keys. You always follow the requested JSON output shape exactly, "
        "with no markdown fences, no commentary, and no text outside the "
        "JSON array."
    )


def _footer(request: GenerationRequest, json_shape: str) -> str:
    subject_note = SUBJECT_NOTES.get(request.subject, "")
    topic_line = f'\nFocus on the sub-topic: "{request.topic}".' if request.topic else ""
    return f"""
{subject_note}{topic_line}

Return ONLY a JSON array of exactly {request.count} objects, each matching this shape:
[{json_shape}, ...]

Do not include the "id", "subject", "chapter", "type", "marks", or "difficulty"
fields in your output — those are filled in by the caller. Do not wrap the
array in markdown code fences. Do not include any text before or after the
JSON array."""


# ---------------------------------------------------------------------------
# Per-(type, marks) templates
# ---------------------------------------------------------------------------

def _prompt_mcq_1_mark(request: GenerationRequest) -> str:
    body = f"""Generate {request.count} multiple-choice questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}, suitable for a Karnataka State Board grade 7-9 student.

For each question return:
- question text
- exactly 4 options (no duplicates, only one correct)
- the correct option, copied verbatim into "answer"
- a 1-line justification for the correct answer in "explanation\""""
    return body + _footer(request, _JSON_SHAPE_MCQ)


def _prompt_short_2_marks(request: GenerationRequest) -> str:
    body = f"""Generate {request.count} short-answer questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}. Each answer must be 1-2 lines long and include exactly one supporting reason or point, matching how a 2-mark answer is evaluated on a Karnataka State Board exam. Do not pad the answer beyond what a 2-mark response would contain."""
    return body + _footer(request, _JSON_SHAPE_DESCRIPTIVE)


def _prompt_short_3_marks(request: GenerationRequest) -> str:
    body = f"""Generate {request.count} questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}. Each answer must contain EXACTLY 3 distinct points or steps (number them 1., 2., 3. inside the "answer" string), matching how a 3-mark answer is evaluated on a Karnataka State Board exam."""
    return body + _footer(request, _JSON_SHAPE_DESCRIPTIVE)


def _prompt_long_5_marks(request: GenerationRequest) -> str:
    body = f"""Generate {request.count} questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}. Each answer must be a detailed, structured response worth full marks on a Karnataka State Board 5-mark question: include multiple points or steps (at least 4), and reference a diagram/example where relevant. Structure the answer explicitly with labeled sections or numbered steps inside the "answer" string (e.g. "1) ... 2) ... 3) ..." or "Causes: ... Effects: ...") rather than leaving the structure implicit."""
    return body + _footer(request, _JSON_SHAPE_DESCRIPTIVE)


# (type, marks) -> builder function
_TEMPLATES = {
    (QuestionType.MCQ, 1): _prompt_mcq_1_mark,
    (QuestionType.SHORT, 2): _prompt_short_2_marks,
    (QuestionType.SHORT, 3): _prompt_short_3_marks,
    (QuestionType.LONG, 5): _prompt_long_5_marks,
}


def build_prompt(request: GenerationRequest) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for the given request.
    Raises KeyError if no template exists for this (type, marks) pair —
    callers should validate the combination before calling this (see
    validation.validate_request_combination).
    """
    key = (request.type, request.marks)
    builder = _TEMPLATES[key]
    return _base_system_prompt(), builder(request)
