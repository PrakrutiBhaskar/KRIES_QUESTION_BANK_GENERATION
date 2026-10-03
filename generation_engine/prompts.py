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

from .schemas import GenerationRequest, QuestionType, figure_ref_map
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
        "You are an expert Karnataka State Board (KSEEB / KTBS) question "
        "paper setter. You write exam questions with answer keys that stay "
        "STRICTLY within the Karnataka State Board syllabus: only content "
        "that appears in the Karnataka Textbook Society (KTBS) textbook for "
        "the stated class, subject and chapter. You never draw on another "
        "board's syllabus or a higher or lower class's content, never use "
        "outside material, and never name other boards or their textbooks. "
        "You use the terminology, units, examples and Indian/Karnataka "
        "context that the KTBS textbook uses. You always follow the "
        "requested JSON output shape exactly, with no markdown fences, no "
        "commentary, and no text outside the JSON object."
    )


_PASSAGE_FIELD = (
    '  "passage": "integer — the [P#] number of the textbook passage this '
    'question is based on",\n'
)


def _with_passage_field(json_shape: str) -> str:
    return json_shape.replace('  "topic"', _PASSAGE_FIELD + '  "topic"', 1)


def _source_block(passages: list, max_chars: int) -> str:
    """The textbook text the questions must be written from — the only permitted source."""
    parts = [
        "\nSOURCE TEXTBOOK PASSAGES (Karnataka Textbook Society, "
        "Class {grade}). These passages are the ONLY permitted source. Write "
        "EXACTLY ONE question per passage, in order: question i must be "
        "answerable from passage [Pi] alone and must test what that passage "
        "teaches. Do not use facts, definitions, figures or examples that are "
        "not in or directly implied by the passage. For numerical subjects you "
        "may change the numbers of a worked example, but the concept, method "
        "and terminology must come from the passage. Set \"passage\" to i."
    ]
    for i, ps in enumerate(passages, 1):
        text = ps.text if len(ps.text) <= max_chars else ps.text[:max_chars].rsplit(" ", 1)[0] + " …"
        parts.append(f"\n[P{i}] (section: {ps.section})\n{text}")
    return "\n".join(parts)


def _figure_block(request: GenerationRequest) -> str:
    """Prompt section describing the stored figures the questions must be about.

    The model is given text only (caption, topic, labelled parts) and is told to
    treat it as the complete truth about the diagram. The caller attaches the
    real figure id from the short reference the model returns.
    """
    refs = figure_ref_map(request.figures)
    if not refs:
        return ""
    listing = "\n".join(f"{ref} - {fig.describe()}" for ref, fig in refs.items())
    return f"""

Figures. Every question must be written about exactly ONE of the figures below. You cannot see the images: each description is all you know about its figure, so treat it as complete and correct.

{listing}

Rules for figure questions:
- Put the reference of the figure the question is about ({", ".join(refs)}) in "figure_ref". Spread the questions over the figures as evenly as you can.
- Ask only what the description supports, such as identifying a labelled part, stating its function, or explaining a stage or relationship it lists. Do NOT invent parts, labels, numbers, positions or colours that are not in the description, and do not describe what the picture looks like beyond it.
- Refer to the diagram inside the question ("In the figure shown ...", "the part labelled A ...") so it reads correctly when printed beside the figure. Do not paste the caption or the full list of labels into the question.
- If a question asks the student to identify a part, refer to that part by its letter or number only. The question must never contain its own answer."""


def _json_shape_for(request: GenerationRequest, json_shape: str) -> str:
    """Add the `figure_ref` field to the JSON shape when figures are in play."""
    if not request.figures:
        return json_shape
    return json_shape.replace(
        '"text": "string",',
        '"text": "string",\n  "figure_ref": "string (reference of the figure this question is about, e.g. F1)",',
        1,
    )


def _scope_block(
    request: GenerationRequest, chapter_topics: Optional[list[str]]
) -> str:
    lines = [
        "\nSYLLABUS SCOPE (mandatory): Karnataka State Board, "
        f"Class {request.grade}, {request.subject.value}, chapter "
        f'"{request.chapter}". Every question and answer must be answerable '
        "from this chapter of the KTBS textbook alone. Do not use concepts, "
        "formulae, theorems, events or vocabulary from other chapters, other "
        "classes or other boards. If you are unsure a point is in this "
        "chapter, leave it out."
    ]
    if chapter_topics and not request.topic:
        lines.append(
            "Topics covered in this chapter (spread questions across them, "
            "and do not go beyond them): " + "; ".join(chapter_topics) + "."
        )
    return "\n".join(lines)


def _footer(
    request: GenerationRequest,
    json_shape: str,
    retry_feedback: Optional[list[str]] = None,
    chapter_topics: Optional[list[str]] = None,
    passages: Optional[list] = None,
    max_passage_chars: int = 900,
) -> str:
    subject_note = get_prompt_note(request.subject)
    grade_line = (
        f"\nTarget grade: Karnataka State Board Class {request.grade}."
        + _scope_block(request, None if passages else chapter_topics)
    )
    if passages:
        grade_line += _source_block(passages, max_passage_chars).replace(
            "{grade}", str(request.grade)
        )
        json_shape = _with_passage_field(json_shape)
    figure_block = _figure_block(request)
    json_shape = _json_shape_for(request, json_shape)
    topic_line = (
        f'\nFocus on the sub-topic: "{request.topic}".' if request.topic else ""
    )

    feedback_block = ""
    if retry_feedback:
        bullets = "\n".join(f"- {r}" for r in retry_feedback[:6])
        feedback_block = (
            "\n\nA previous attempt was rejected for the following reasons. "
            "Fix all of them in this batch, but do NOT change the JSON "
            "shape while doing so: the array must still contain exactly "
            "one complete question object per item, with every required "
            "field. If a fix means adding more detail, more steps, or "
            "numbered points, put that content INSIDE the relevant "
            "object's string field (usually \"answer\") — never as "
            "separate bare strings replacing the objects themselves:\n"
            + bullets
        )

    return f"""
{subject_note}{grade_line}{topic_line}{figure_block}{feedback_block}

Return ONLY a JSON object with a single key "questions", whose value is a JSON array of exactly {request.count} objects (one object per question, even when the count is 1), each matching this shape:
{{"questions": [{json_shape}, ...]}}

Every question in the array must be distinct — do not rephrase the same
question twice. Do not include the "id", "subject", "chapter", "type",
"grade", "marks", or "difficulty" fields in your output — those are filled
in by the caller. Do not wrap the JSON in markdown code fences. Do not
include any text before or after the JSON object."""


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

This numbering is INSIDE each object's "answer" field only — it has nothing to do with how many objects are in the outer array (that count is always {request.count}, one object per question). Within each "answer" string, number the three points "1. ", "2. ", "3. ", each on its own line. Do not merge two points into one, and do not add a fourth."""


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
    chapter_topics: Optional[list[str]] = None,
    passages: Optional[list] = None,
    max_passage_chars: int = 900,
) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for the given request.

    `chapter_topics` are the syllabus' sub-topics for the chapter (from
    SyllabusIndex.topics); when given they bound the questions' scope.

    `passages` are the textbook passages assigned to this batch (one per
    question, len == request.count). When given, questions must be written from
    them and each must report which passage it used.

    `retry_feedback` is an optional list of reasons a previous attempt was
    rejected; when supplied it's appended to the prompt so the model corrects
    course instead of resampling blindly.

    Raises KeyError if no template exists for this (type, marks) pair —
    callers should validate the combination first (see
    validation.validate_request_combination).
    """
    builder, json_shape = _TEMPLATES[(request.type, request.marks)]
    user_prompt = builder(request) + _footer(
        request, json_shape, retry_feedback, chapter_topics, passages, max_passage_chars
    )
    return _base_system_prompt(), user_prompt
