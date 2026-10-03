"""Figure requests and textbook grounding are two different grounding sources.

A figure question is written from the figure's own metadata, so it must not be
refused (or fed passages) just because REQUIRE_TEXTBOOK is on.
"""
import dataclasses

import pytest

from generation_engine import engine as engine_module
from generation_engine.engine import GenerationEngine
from generation_engine.exceptions import InvalidRequestError
from generation_engine.schemas import (
    Difficulty,
    FigureContext,
    GenerationRequest,
    QuestionType,
    Subject,
)
from generation_engine.textbook import TextbookCorpus

CELL = FigureContext(
    id="11111111-1111-1111-1111-111111111111",
    caption="Plant cell",
    labels=["A: nucleus", "B: cell wall"],
)


class ScriptedGroq:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    async def complete_json(self, system_prompt, user_prompt):
        self.prompts.append(user_prompt)
        return self.payload


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(
        engine_module,
        "settings",
        dataclasses.replace(
            engine_module.settings,
            enable_llm_answer_verification=False,
            max_regeneration_retries=0,
        ),
    )


def _request(**kw):
    base = dict(
        subject=Subject.SCIENCE,
        chapter="Cell Structure",
        type=QuestionType.SHORT,
        grade=8,
        marks=2,
        difficulty=Difficulty.MEDIUM,
        count=1,
    )
    base.update(kw)
    return GenerationRequest(**base)


async def test_figure_request_is_not_refused_by_require_textbook():
    client = ScriptedGroq(
        [
            {
                "text": "In the figure shown, what is the function of the part labelled A?",
                "answer": "It controls the activities of the cell. It holds the genetic material.",
                "explanation": "",
                "topic": "Cell",
                "tags": [],
                "figure_ref": "F1",
            }
        ]
    )
    engine = GenerationEngine(
        groq_client=client, textbooks=TextbookCorpus(), require_textbook=True
    )
    questions, _ = await engine.generate(_request(figures=[CELL]))
    assert questions[0].figure_id == CELL.id
    assert "SOURCE TEXTBOOK PASSAGES" not in client.prompts[0]


async def test_plain_request_is_still_refused_without_a_textbook():
    engine = GenerationEngine(
        groq_client=ScriptedGroq([]), textbooks=TextbookCorpus(), require_textbook=True
    )
    with pytest.raises(InvalidRequestError, match="textbook"):
        await engine.generate(_request())
