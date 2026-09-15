"""
Exceptions raised by the generation engine.

These map directly onto the error contract in api-contract.md so the Backend
router can translate them into HTTP responses with almost no logic:

    InvalidRequestError       -> 400  {"error": "...", "detail": "..."}
    GroqAPIError               -> 502  {"error": "...", "detail": "..."}
    GenerationValidationError  -> 422  {"error": "...", "detail": "..."}

Example FastAPI wiring (Module B):

    @router.post("/generate")
    async def generate(req: GenerationRequest):
        try:
            questions = await engine.generate(req)
        except InvalidRequestError as e:
            raise HTTPException(400, detail={"error": e.error, "detail": str(e)})
        except GroqAPIError as e:
            raise HTTPException(502, detail={"error": e.error, "detail": str(e)})
        except GenerationValidationError as e:
            raise HTTPException(422, detail={"error": e.error, "detail": str(e)})
        return {"questions": [q.model_dump() for q in questions]}
"""
from __future__ import annotations

from typing import Any, Optional


class GenerationEngineError(Exception):
    """Base class for all generation-engine errors."""

    error: str = "generation_error"

    def __init__(self, detail: str, context: Optional[dict[str, Any]] = None):
        self.detail = detail
        self.context = context or {}
        super().__init__(detail)


class InvalidRequestError(GenerationEngineError):
    """Invalid subject/chapter/type/marks combination. Maps to HTTP 400."""

    error = "invalid_request"


class GroqAPIError(GenerationEngineError):
    """The Groq API call failed or timed out. Maps to HTTP 502."""

    error = "groq_api_error"


class GenerationValidationError(GenerationEngineError):
    """
    Generated output failed validation after all retries — schema mismatch,
    duplicate content, or marks/answer length mismatch. Maps to HTTP 422.
    """

    error = "validation_failed"
