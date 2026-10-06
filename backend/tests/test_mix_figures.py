"""`mix_figures`: the server randomly makes some questions diagram-based."""
from __future__ import annotations

import pytest

from .test_figure_generation_api import BASE, add_figure, generate

pytestmark = pytest.mark.asyncio


async def test_mix_figures_gives_diagram_and_theory_questions(client, admin_client):
    await add_figure(admin_client)
    r = await generate(client, mix_figures=True, count=6, refresh=True)
    assert r.status_code == 200, r.text
    items = r.json()["questions"]
    figure = [q for q in items if q.get("figure")]
    assert figure, "no diagram-based question"
    assert len(figure) < len(items), "no theory question"
    assert len(items) <= 6


async def test_mix_figures_is_all_theory_when_the_chapter_has_no_figure(client):
    r = await generate(client, mix_figures=True, count=4, refresh=True)
    assert r.status_code == 200, r.text
    assert not [q for q in r.json()["questions"] if q.get("figure")]


async def test_without_mix_figures_nothing_is_diagram_based(client, admin_client):
    await add_figure(admin_client)
    r = await generate(client, count=4, refresh=True)
    assert r.status_code == 200, r.text
    assert not [q for q in r.json()["questions"] if q.get("figure")]
