"""A blueprint paper is always a mix of diagram-based and theory questions."""
from __future__ import annotations

import pytest

from app.services.blueprint import figure_share

from .test_blueprint import blueprint
from .test_figure_generation_api import add_figure

pytestmark = pytest.mark.asyncio


def test_figure_share_is_about_a_third_and_never_zero_for_a_real_group():
    assert [figure_share(n) for n in (0, 1, 2, 3, 4, 5, 6, 9, 12)] == [0, 0, 1, 1, 1, 1, 2, 3, 4]


def _split(paper: dict) -> tuple[list[dict], list[dict]]:
    items = paper["questions"]
    figure = [i for i in items if i["question"].get("figure")]
    theory = [i for i in items if not i["question"].get("figure")]
    return figure, theory


async def test_paper_mixes_figure_and_theory_questions(client, admin_client):
    await add_figure(admin_client, chapter="Photosynthesis")
    await add_figure(admin_client, chapter="Respiration", caption="Lungs")

    response = await client.post("/papers/blueprint", json=blueprint())
    assert response.status_code == 201, response.text
    figure, theory = _split(response.json())

    assert figure, "paper has no diagram-based question"
    assert theory, "paper has no theory question"
    assert len(figure) + len(theory) == 17
    # The chapter with no library figure is theory only.
    assert not [i for i in figure if i["question"]["chapter"] == "Transportation"]


async def test_paper_falls_back_to_theory_when_the_library_is_empty(client):
    response = await client.post("/papers/blueprint", json=blueprint())
    assert response.status_code == 201, response.text
    figure, theory = _split(response.json())
    assert figure == [] and len(theory) == 17


async def test_a_paper_of_single_question_groups_still_gets_a_figure_question(client, admin_client):
    await add_figure(admin_client, chapter="Photosynthesis")
    body = blueprint(
        chapters=[{"name": "Photosynthesis", "weightage": 100}],
        sections=[
            {"name": "A", "type": "MCQ", "marks_per_question": 1, "total_marks": 1},
            {"name": "B", "type": "Short", "marks_per_question": 2, "total_marks": 2},
        ],
    )
    response = await client.post("/papers/blueprint", json=body)
    assert response.status_code == 201, response.text
    figure, theory = _split(response.json())
    assert len(figure) == 1 and len(theory) == 1
