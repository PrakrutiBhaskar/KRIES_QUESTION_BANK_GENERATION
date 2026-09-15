"""
Thin async wrapper around the Groq chat-completions API.

Kept deliberately small and swappable: it exposes `complete_json`, which
sends a system+user prompt and returns the parsed JSON payload (a list of
question objects). Any network error, non-2xx response, or invalid JSON is
normalized into a `GroqAPIError` so the rest of the engine never has to know
about httpx/Groq specifics.

Transient failures (429 rate limits, 5xx, timeouts) are retried with
exponential backoff before giving up — a single rate-limit blip shouldn't
surface to the user as a 502.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from .config import settings
from .exceptions import GroqAPIError

logger = logging.getLogger("generation_engine.groq")

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _strip_markdown_fence(text: str) -> str:
    """Models sometimes wrap JSON in ```json ... ``` despite instructions not to."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


class GroqClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        temperature: float | None = None,
        max_retries: int | None = None,
        retry_backoff: float | None = None,
    ):
        self.api_key = api_key or settings.groq_api_key
        self.base_url = (base_url or settings.groq_base_url).rstrip("/")
        self.model = model or settings.groq_model
        self.timeout = timeout or settings.groq_timeout_seconds
        self.temperature = (
            temperature if temperature is not None else settings.groq_temperature
        )
        self.max_retries = (
            max_retries if max_retries is not None else settings.groq_max_retries
        )
        self.retry_backoff = (
            retry_backoff
            if retry_backoff is not None
            else settings.groq_retry_backoff_seconds
        )

    async def complete_json(
        self, system_prompt: str, user_prompt: str
    ) -> list[dict[str, Any]]:
        """
        Sends the prompt pair to Groq and returns the parsed JSON array.
        Raises GroqAPIError on any network failure, non-2xx response, or
        output that isn't valid/parseable JSON.
        """
        if not self.api_key:
            raise GroqAPIError("GROQ_API_KEY is not configured")

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            # Ask Groq to constrain decoding to valid JSON. The prompt asks for
            # a top-level array, which json_object mode won't guarantee, so the
            # parser below still handles an object wrapping the array.
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        content = await self._post_with_retries(payload, headers)
        return self._parse_json_array(content)

    async def _post_with_retries(self, payload: dict, headers: dict) -> str:
        last_error: str = "unknown error"
        attempts = self.max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
            except httpx.TimeoutException as e:
                last_error = f"Groq API call timed out after {self.timeout}s"
                if attempt == attempts:
                    raise GroqAPIError(last_error) from e
            except httpx.HTTPError as e:
                last_error = f"Groq API call failed: {e}"
                if attempt == attempts:
                    raise GroqAPIError(last_error) from e
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = (
                        f"Groq API returned {response.status_code}: "
                        f"{response.text[:500]}"
                    )
                    if attempt == attempts:
                        raise GroqAPIError(last_error)
                elif response.status_code >= 400:
                    # Non-retryable (bad key, bad model, malformed request).
                    raise GroqAPIError(
                        f"Groq API returned {response.status_code}: "
                        f"{response.text[:500]}"
                    )
                else:
                    try:
                        body = response.json()
                        return body["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, ValueError) as e:
                        raise GroqAPIError(
                            f"Unexpected Groq response shape: {e}"
                        ) from e

            delay = self._backoff_delay(attempt)
            logger.warning(
                "Groq call attempt %d/%d failed (%s); retrying in %.1fs",
                attempt,
                attempts,
                last_error,
                delay,
            )
            await asyncio.sleep(delay)

        raise GroqAPIError(last_error)  # pragma: no cover - loop always returns/raises

    def _backoff_delay(self, attempt: int) -> float:
        return self.retry_backoff * (2 ** (attempt - 1))

    @staticmethod
    def _parse_json_array(content: str) -> list[dict[str, Any]]:
        cleaned = _strip_markdown_fence(content)
        parsed: Any
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fall back to extracting the first [...] block in case the model
            # added stray commentary despite instructions.
            match = _JSON_ARRAY_RE.search(cleaned)
            if not match:
                raise GroqAPIError("Groq response was not valid JSON")
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise GroqAPIError(f"Groq response was not valid JSON: {e}") from e

        # json_object response mode returns an object, so the array is often
        # nested under a single key ({"questions": [...]}). Unwrap it.
        if isinstance(parsed, dict):
            for value in parsed.values():
                if isinstance(value, list):
                    parsed = value
                    break
            else:
                # A single question object returned bare, not in an array.
                if "text" in parsed:
                    parsed = [parsed]

        if not isinstance(parsed, list):
            raise GroqAPIError("Groq response JSON was not an array")
        return parsed
