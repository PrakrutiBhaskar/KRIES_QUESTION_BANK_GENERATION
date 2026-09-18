"""
Generation Engine — Module A of the Question Bank Generator.

Turns a (subject, chapter, type, marks, difficulty, count) request into a
validated batch of `Question` objects, ready for the Backend (Module B) to
persist and serve.

Public API:
    GenerationEngine    — orchestrates prompt -> Groq call -> validation
    GenerationRequest   — input shape, mirrors POST /generate body
    Question            — shared output shape, mirrors api-contract.md
    GroqClient          — thin async wrapper around the Groq chat API
    SyllabusIndex       — optional Subject -> Chapter lookup for 400 checks
    SubjectFormat       — per-subject marks-to-format configuration

Exceptions map 1:1 onto the error contract in api-contract.md:
    InvalidRequestError      -> HTTP 400
    GroqAPIError              -> HTTP 502
    GenerationValidationError -> HTTP 422

Usage:
    engine = GenerationEngine()
    questions, report = await engine.generate(request)
"""

from .schemas import (
    Question,
    GenerationRequest,
    Subject,
    QuestionType,
    Difficulty,
    VALID_MARKS,
    VALID_MARKS_BY_TYPE,
    VALID_GRADES,
)
from .exceptions import (
    GenerationEngineError,
    InvalidRequestError,
    GroqAPIError,
    GenerationValidationError,
)
from .config import Settings, settings, reload_settings
from .groq_client import GroqClient
from .engine import GenerationEngine, GenerationReport
from .difficulty import estimate_difficulty, flag_difficulty_mismatch
from .prompts import build_prompt, supported_combinations
from .syllabus import SyllabusIndex
from .syllabus_ingest import (
    extract_chapters_from_pdf,
    extract_chapters_from_text,
    merge_chapters,
)
from .subject_formats import (
    MarksRule,
    SubjectFormat,
    get_marks_rule,
    get_prompt_note,
    register_subject_format,
)
from .validation import (
    build_question,
    check_answer_relevance,
    check_marks_format,
    find_duplicates,
    validate_batch,
    validate_request_combination,
)

__all__ = [
    # schemas
    "Question",
    "GenerationRequest",
    "Subject",
    "QuestionType",
    "Difficulty",
    "VALID_MARKS",
    "VALID_MARKS_BY_TYPE",
    "VALID_GRADES",
    # errors
    "GenerationEngineError",
    "InvalidRequestError",
    "GroqAPIError",
    "GenerationValidationError",
    # config
    "Settings",
    "settings",
    "reload_settings",
    # core
    "GroqClient",
    "GenerationEngine",
    "GenerationReport",
    "build_prompt",
    "supported_combinations",
    "SyllabusIndex",
    "extract_chapters_from_pdf",
    "extract_chapters_from_text",
    "merge_chapters",
    # difficulty
    "estimate_difficulty",
    "flag_difficulty_mismatch",
    # subject configuration
    "MarksRule",
    "SubjectFormat",
    "get_marks_rule",
    "get_prompt_note",
    "register_subject_format",
    # validation
    "build_question",
    "check_answer_relevance",
    "check_marks_format",
    "find_duplicates",
    "validate_batch",
    "validate_request_combination",
]
