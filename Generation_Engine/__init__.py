"""
Generation Engine — Module A of the Question Bank Generator.

Turns a (subject, chapter, type, marks, difficulty, count) request into a
validated batch of `Question` objects, ready for the Backend (Module B) to
persist and serve.

Public API:
    GenerationEngine   — orchestrates prompt -> Groq call -> validation
    GenerationRequest  — input shape, mirrors POST /generate body
    Question            — shared output shape, mirrors api-contract.md
    GroqClient          — thin async wrapper around the Groq chat API

Exceptions map 1:1 onto the error contract in api-contract.md:
    InvalidRequestError      -> HTTP 400
    GroqAPIError              -> HTTP 502
    GenerationValidationError -> HTTP 422
"""

from .schemas import (
    Question,
    GenerationRequest,
    Subject,
    QuestionType,
    Difficulty,
    VALID_MARKS,
    VALID_MARKS_BY_TYPE,
)
from .exceptions import (
    GenerationEngineError,
    InvalidRequestError,
    GroqAPIError,
    GenerationValidationError,
)
from .groq_client import GroqClient
from .engine import GenerationEngine
from .difficulty import estimate_difficulty

__all__ = [
    "Question",
    "GenerationRequest",
    "Subject",
    "QuestionType",
    "Difficulty",
    "VALID_MARKS",
    "VALID_MARKS_BY_TYPE",
    "GenerationEngineError",
    "InvalidRequestError",
    "GroqAPIError",
    "GenerationValidationError",
    "GroqClient",
    "GenerationEngine",
    "estimate_difficulty",
]
