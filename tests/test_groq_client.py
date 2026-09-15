"""
GroqClient tests — JSON parsing robustness and transport retry behaviour.
All HTTP is faked via monkeypatched httpx.AsyncClient; nothing hits the network.
"""
import json

import httpx
import pytest

from generation_engine.exceptions import GroqAPIError
from generation_engine.groq_client import GroqClient


# --- fake transport ------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def groq_body(content: str):
    return {"choices": [{"message": {"content": content}}]}


class FakeAsyncClient:
    """Replaces httpx.AsyncClient; replays a scripted list of responses."""

    script = []
    call_count = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        item = FakeAsyncClient.script[
            min(FakeAsyncClient.call_count, len(FakeAsyncClient.script) - 1)
        ]
        FakeAsyncClient.call_count += 1
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_http(monkeypatch):
    FakeAsyncClient.script = []
    FakeAsyncClient.call_count = 0
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


@pytest.fixture
def client():
    return GroqClient(api_key="test-key", max_retries=2, retry_backoff=0.0)


# --- parsing -------------------------------------------------------------


def test_parses_plain_array():
    out = GroqClient._parse_json_array('[{"text": "Q1"}, {"text": "Q2"}]')
    assert len(out) == 2


def test_strips_markdown_fences():
    out = GroqClient._parse_json_array('```json\n[{"text": "Q1"}]\n```')
    assert out[0]["text"] == "Q1"


def test_unwraps_object_wrapper_from_json_mode():
    """response_format=json_object forces an object, so the array is nested."""
    out = GroqClient._parse_json_array('{"questions": [{"text": "Q1"}]}')
    assert out[0]["text"] == "Q1"


def test_wraps_single_bare_object():
    out = GroqClient._parse_json_array('{"text": "Q1", "answer": "A"}')
    assert isinstance(out, list) and len(out) == 1


def test_recovers_array_from_surrounding_commentary():
    out = GroqClient._parse_json_array('Sure! [{"text": "Q1"}] Hope that helps.')
    assert out[0]["text"] == "Q1"


def test_unparseable_content_raises():
    with pytest.raises(GroqAPIError):
        GroqClient._parse_json_array("not json at all")


# --- transport -----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_raises():
    with pytest.raises(GroqAPIError):
        await GroqClient(api_key="").complete_json("sys", "user")


@pytest.mark.asyncio
async def test_successful_call_returns_parsed_array(fake_http, client):
    fake_http.script = [FakeResponse(200, groq_body('[{"text": "Q1"}]'))]
    out = await client.complete_json("sys", "user")
    assert out[0]["text"] == "Q1"


@pytest.mark.asyncio
async def test_rate_limit_is_retried_then_succeeds(fake_http, client):
    fake_http.script = [
        FakeResponse(429, text="rate limited"),
        FakeResponse(200, groq_body('[{"text": "Q1"}]')),
    ]
    out = await client.complete_json("sys", "user")
    assert out[0]["text"] == "Q1"
    assert fake_http.call_count == 2


@pytest.mark.asyncio
async def test_persistent_5xx_raises_after_retries(fake_http, client):
    fake_http.script = [FakeResponse(503, text="unavailable")]
    with pytest.raises(GroqAPIError):
        await client.complete_json("sys", "user")
    assert fake_http.call_count == 3  # max_retries=2 -> 3 attempts


@pytest.mark.asyncio
async def test_auth_error_is_not_retried(fake_http, client):
    fake_http.script = [FakeResponse(401, text="bad key")]
    with pytest.raises(GroqAPIError):
        await client.complete_json("sys", "user")
    assert fake_http.call_count == 1


@pytest.mark.asyncio
async def test_timeout_raises_groq_api_error(fake_http, client):
    fake_http.script = [httpx.TimeoutException("timed out")]
    with pytest.raises(GroqAPIError):
        await client.complete_json("sys", "user")
