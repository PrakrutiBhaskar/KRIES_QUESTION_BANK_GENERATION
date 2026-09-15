"""
Thin async wrapper around the Groq chat-completions API.

Kept deliberately small and swappable: it exposes one method,
`complete_json`, which sends a system+user prompt and returns the parsed
JSON payload (expected to be a JSON array of question objects). Any network
error, non-2xx response, or invalid JSON is normalized into a `GroqAPIError`
so the rest of the engine never has to know about httpx/Groq specifics.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import settings
from .exceptions import GroqAPIError

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


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
    ):
        self.api_key = api_key or settings.groq_api_key
        self.base_url = (base_url or settings.groq_base_url).rstrip("/")
        self.model = model or settings.groq_model
        self.timeout = timeout or settings.groq_timeout_seconds
        self.temperature = temperature if temperature is not None else settings.groq_temperature

    async def complete_json(self, system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
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
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as e:
            raise GroqAPIError(f"Groq API call timed out after {self.timeout}s") from e
        except httpx.HTTPError as e:
            raise GroqAPIError(f"Groq API call failed: {e}") from e

        if response.status_code >= 400:
            raise GroqAPIError(
                f"Groq API returned {response.status_code}: {response.text[:500]}"
            )

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise GroqAPIError(f"Unexpected Groq response shape: {e}") from e

        return self._parse_json_array(content)

    @staticmethod
    def _parse_json_array(content: str) -> list[dict[str, Any]]:
        cleaned = _strip_markdown_fence(content)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fall back to extracting the first [...] block in case the
            # model added stray commentary despite instructions.
            match = _JSON_ARRAY_RE.search(cleaned)
            if not match:
                raise GroqAPIError("Groq response was not valid JSON")
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise GroqAPIError(f"Groq response was not valid JSON: {e}") from e

        if not isinstance(parsed, list):
            raise GroqAPIError("Groq response JSON was not an array")
        return parsed
