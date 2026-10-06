"""The Grade 8 Science diagram set (backend/data/figures/grade8) loads, and loads alongside Grade 7."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

FIGURES = Path(__file__).resolve().parents[1] / "data" / "figures"


def _entries(grade: int) -> list[dict]:
    return json.loads((FIGURES / f"grade{grade}" / "manifest.json").read_text(encoding="utf-8"))["figures"]


async def _upload(admin_client, grade: int) -> None:
    folder = FIGURES / f"grade{grade}"
    for e in _entries(grade):
        r = await admin_client.post(
            "/figures",
            files={"file": (e["file"], (folder / e["file"]).read_bytes(), "image/png")},
            data={
                "caption": e["caption"],
                "subject": e["subject"],
                "chapter": e["chapter"],
                "topic": e["topic"],
                "labels": json.dumps(e["labels"]),
            },
        )
        assert r.status_code == 201, (e["file"], r.text)


def test_grade8_manifest_matches_files():
    entries = _entries(8)
    assert len(entries) == 65
    folder = FIGURES / "grade8"
    assert {e["file"] for e in entries} == {p.name for p in folder.glob("*.png")}


def test_grade7_and_grade8_chapters_do_not_overlap():
    # figures are matched to a chapter by name, so a shared name would leak grade 7 figures into grade 8
    assert not {e["chapter"] for e in _entries(7)} & {e["chapter"] for e in _entries(8)}


async def test_every_grade8_figure_uploads(admin_client):
    await _upload(admin_client, 8)
    page = (await admin_client.get("/figures", params={"subject": "Science", "page_size": 100})).json()
    assert page["total"] == 65


async def test_grade7_and_grade8_upload_together(admin_client):
    await _upload(admin_client, 7)
    await _upload(admin_client, 8)
    page = (await admin_client.get("/figures", params={"subject": "Science", "page_size": 100})).json()
    assert page["total"] == len(_entries(7)) + len(_entries(8)) == 118
