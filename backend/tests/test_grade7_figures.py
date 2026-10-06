"""The Grade 7 Science diagram set (backend/data/figures/grade7) loads and drives figure questions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .test_figure_generation_api import BASE, generate

pytestmark = pytest.mark.asyncio

GRADE7 = Path(__file__).resolve().parents[1] / "data" / "figures" / "grade7"


def _entries() -> list[dict]:
    return json.loads((GRADE7 / "manifest.json").read_text(encoding="utf-8"))["figures"]


async def _upload_all(admin_client) -> None:
    for e in _entries():
        r = await admin_client.post(
            "/figures",
            files={"file": (e["file"], (GRADE7 / e["file"]).read_bytes(), "image/png")},
            data={
                "caption": e["caption"],
                "subject": e["subject"],
                "chapter": e["chapter"],
                "topic": e["topic"],
                "labels": json.dumps(e["labels"]),
            },
        )
        assert r.status_code == 201, (e["file"], r.text)


async def test_every_grade7_figure_uploads(admin_client):
    await _upload_all(admin_client)
    page = (await admin_client.get("/figures", params={"subject": "Science", "page_size": 100})).json()
    assert page["total"] == len(_entries()) == 53


async def test_a_grade7_chapter_generates_figure_questions(admin_client, client):
    await _upload_all(admin_client)
    r = await generate(
        client, **{**BASE, "chapter": "Life Processes in Plants", "grade": 7, "use_figures": True, "count": 3}
    )
    assert r.status_code == 200, r.text
    assert all(q.get("figure") for q in r.json()["questions"])
