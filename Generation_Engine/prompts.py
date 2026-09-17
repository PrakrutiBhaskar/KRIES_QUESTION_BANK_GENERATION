"""
Prompt templates — one builder per (type, marks) combination, matching
prompt-library.md. This module is the single place prompts live; keep it in
sync with prompt-library.md whenever a template changes (that doc is the
source of truth for *why* a prompt looks the way it does — this file is the
executable version of it).

Subject-specific guidance is not written here: it comes from
subject_formats.py, which the validation layer reads from too. That shared
source is what keeps "what we asked for" and "what we check for" aligned.

Every prompt asks for strict JSON so the response can be parsed directly
against the `Question` schema.
"""
from __future__ import annotations

from typing import Optional

from .schemas import GenerationRequest, QuestionType
from .subject_formats import get_prompt_note

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
  "explanation": "string (may expand on the answer's reasoning; empty string for 1-mark)",
  "topic": "string (short sub-topic tag within the chapter)",
  "tags": ["string"]
}"""


def _base_system_prompt() -> str:
    return (
        "You are an expert Karnataka State Board question paper setter. "
        "You write syllabus-aligned exam questions with answer keys, "
        "calibrated to whichever grade you're told to target for a given "
        "request. You always follow the requested JSON output shape "
        "exactly, with no markdown fences, no commentary, and no text "
        "outside the JSON array."
    )


def _footer(
    request: GenerationRequest,
    json_shape: str,
    retry_feedback: Optional[list[str]] = None,
) -> str:
    subject_note = get_prompt_note(request.subject)
    grade_line = f"\nTarget grade: Karnataka State Board Class {request.grade}."
    topic_line = (
        f'\nFocus on the sub-topic: "{request.topic}".' if request.topic else ""
    )

    feedback_block = ""
    if retry_feedback:
        bullets = "\n".join(f"- {r}" for r in retry_feedback[:6])
        feedback_block = (
            "\n\nA previous attempt was rejected for the following reasons. "
            "Fix all of them in this batch:\n" + bullets
        )

    return f"""
{subject_note}{grade_line}{topic_line}{feedback_block}

Return ONLY a JSON array of exactly {request.count} objects, each matching this shape:
[{json_shape}, ...]

Every question in the array must be distinct — do not rephrase the same
question twice. Do not include the "id", "subject", "chapter", "type",
"grade", "marks", or "difficulty" fields in your output — those are filled
in by the caller. Do not wrap the array in markdown code fences. Do not
include any text before or after the JSON array."""


# ---------------------------------------------------------------------------
# Per-(type, marks) templates
# ---------------------------------------------------------------------------

def _prompt_mcq_1_mark(request: GenerationRequest) -> str:
    return f"""Generate {request.count} multiple-choice questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}.

For each question return:
- question text
- exactly 4 options (no duplicates, exactly one of them correct)
- the correct option, copied verbatim into "answer"
- a 1-line justification for the correct answer in "explanation\""""


def _prompt_short_1_mark(request: GenerationRequest) -> str:
    return f"""Generate {request.count} one-mark questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}.

Each answer must be a single word, a short phrase, or one direct factual line — the kind of answer a 1-mark question is awarded full marks for (e.g. "What is the SI unit of force?" -> "Newton"). Do NOT explain, justify, or add working. Leave "explanation" as an empty string."""


def _prompt_short_2_marks(request: GenerationRequest) -> str:
    return f"""Generate {request.count} short-answer questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}. Each answer must be 1-2 lines long and include exactly one supporting reason or point, matching how a 2-mark answer is evaluated on a Karnataka State Board exam. Do not pad the answer beyond what a 2-mark response would contain."""


def _prompt_short_3_marks(request: GenerationRequest) -> str:
    return f"""Generate {request.count} questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}. Each answer must contain EXACTLY 3 distinct points or steps, matching how a 3-mark answer is evaluated on a Karnataka State Board exam.

Number the three points inside the "answer" string as "1. ", "2. ", "3. " and put each on its own line. Do not merge two points into one, and do not add a fourth."""


def _prompt_long_5_marks(request: GenerationRequest) -> str:
    return f"""Generate {request.count} questions for {request.subject.value}, chapter "{request.chapter}", difficulty {request.difficulty.value}. Each answer must be a detailed, structured response worth full marks on a Karnataka State Board 5-mark question: at least 4 distinct points or steps, and a reference to a diagram or worked example where relevant.

Structure the answer explicitly inside the "answer" string — numbered steps each on their own line ("1. ... 2. ... 3. ..."), or labeled sections ("Causes: ... Effects: ...") — rather than leaving the structure implicit in a single paragraph."""


# (type, marks) -> builder function
_TEMPLATES = {
    (QuestionType.MCQ, 1): (_prompt_mcq_1_mark, _JSON_SHAPE_MCQ),
    (QuestionType.SHORT, 1): (_prompt_short_1_mark, _JSON_SHAPE_DESCRIPTIVE),
    (QuestionType.SHORT, 2): (_prompt_short_2_marks, _JSON_SHAPE_DESCRIPTIVE),
    (QuestionType.SHORT, 3): (_prompt_short_3_marks, _JSON_SHAPE_DESCRIPTIVE),
    (QuestionType.LONG, 5): (_prompt_long_5_marks, _JSON_SHAPE_DESCRIPTIVE),
}


def supported_combinations() -> list[tuple[QuestionType, int]]:
    return sorted(_TEMPLATES.keys(), key=lambda k: (k[0].value, k[1]))


def build_prompt(
    request: GenerationRequest,
    retry_feedback: Optional[list[str]] = None,
) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for the given request.

    `retry_feedback` is an optional list of reasons a previous attempt was
    rejected; when supplied it's appended to the prompt so the model corrects
    course instead of resampling blindly.

    Raises KeyError if no template exists for this (type, marks) pair —
    callers should validate the combination first (see
    validation.validate_request_combination).
    """
    builder, json_shape = _TEMPLATES[(request.type, request.marks)]
    user_prompt = builder(request) + _footer(request, json_shape, retry_feedback)
    return _base_system_prompt(), user_prompt
