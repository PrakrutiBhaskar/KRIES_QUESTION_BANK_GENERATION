#!/usr/bin/env python3
"""
Seed previous / model question papers into the question bank.

Reads a JSON file from backend/data/model_papers/ and stores every question the
same way POST /generate does (get-or-create chapter, content-hash duplicate
guard, validated through the engine's Question model), so re-running is safe and
the rows show up in GET /questions and in the cache that /generate draws from.

Rows are tagged "previous-paper" so they can be told apart from generated ones.

Skipped, and listed in the summary rather than stored wrongly:
  * questions whose chapter is null (could not be matched to the syllabus), and
  * 4-mark questions: the system only allows marks 1, 2, 3 and 5 (CHECK
    constraint ck_questions_marks and VALID_MARKS). Use --four-mark-as 5 (or 3)
    to store them at that weight instead.

Examples (run from the repo root, with DATABASE_URL pointing at your database):
    python backend/scripts/seed_model_papers.py --dry-run
    python backend/scripts/seed_model_papers.py
    python backend/scripts/seed_model_papers.py --file backend/data/model_papers/sa2_grade7_en.json --four-mark-as 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.db import Base, SessionLocal, engine, ensure_schema  # noqa: E402
from app.services.questions import persist_batch  # noqa: E402
from app.services.syllabus import get_syllabus_index, load_syllabus_index, resolve_chapter  # noqa: E402
from generation_engine.schemas import Question as EngineQuestion  # noqa: E402
from generation_engine.schemas import Subject  # noqa: E402

DEFAULT_FILE = ROOT / "backend" / "data" / "model_papers" / "sa2_grade7_en.json"
KEY_NOTE = "Taken from a model question paper. The paper has no answer key; the answer was drafted separately and has not been checked by the board."


def build(raw: dict, grade: int, four_mark_as: str):
    """Return (EngineQuestion | None, skip_reason | None)."""
    if not raw.get("chapter"):
        return None, "no chapter matched in the syllabus" + (f" (likely textbook chapter: {raw['chapter_guess']})" if raw.get("chapter_guess") else "")
    marks = raw["marks"]
    if marks == 4:
        if four_mark_as == "skip":
            return None, "4 marks is not an allowed mark value"
        marks = int(four_mark_as)
    note = KEY_NOTE + (f" Review: {raw['review']}" if raw.get("review") else "")
    q = EngineQuestion(
        subject=Subject(raw["subject"]),
        chapter=raw["chapter"],
        type=raw["type"],
        grade=raw.get("grade", grade),
        text=raw["text"],
        options=raw.get("options"),
        answer=raw["answer"],
        explanation=raw.get("explanation") or "",
        marks=marks,
        difficulty=raw["difficulty"],
        topic=raw.get("topic") or "",
        tags=list(raw.get("tags") or []) + ([f"paper-q:{raw['paper_q']}"] if raw.get("paper_q") else []),
        verification_status="unverified",
        verification_note=note[:1000],
    )
    return q, None


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    ap.add_argument("--four-mark-as", choices=["skip", "3", "5"], default="skip")
    ap.add_argument("--dry-run", action="store_true", help="validate and report, write nothing")
    args = ap.parse_args()

    data = json.loads(args.file.read_text(encoding="utf-8"))
    grade = data.get("grade", 7)
    load_syllabus_index()
    index = get_syllabus_index()

    ready: dict[tuple[str, str], list[EngineQuestion]] = defaultdict(list)
    skipped: list[str] = []
    for raw in data["questions"]:
        label = f"{raw['subject']} {raw.get('paper_q', '?')}"
        try:
            q, why = build(raw, grade, args.four_mark_as)
        except ValueError as e:
            skipped.append(f"{label}: invalid ({str(e).splitlines()[0][:120]})")
            continue
        if q is None:
            skipped.append(f"{label}: {why}")
            continue
        if index is not None and not index.has_chapter(q.subject, q.chapter, q.grade):
            skipped.append(f"{label}: chapter '{q.chapter}' is not in the Grade {q.grade} {q.subject.value} syllabus")
            continue
        ready[(q.subject.value, q.chapter)].append(q)

    total = sum(len(v) for v in ready.values())
    print(f"{total} questions ready, {len(skipped)} skipped")

    stored = 0
    if not args.dry_run and total:
        async with engine.begin() as conn:  # no-op on an up-to-date database
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(ensure_schema)
        async with SessionLocal() as session:
            for (subject, chapter), qs in ready.items():
                row = await resolve_chapter(session, Subject(subject), chapter)
                stored += len(await persist_batch(session, qs, chapter=row))
            await session.commit()
        print(f"stored {stored} (already-present questions are reused, not duplicated)")

    for s in skipped:
        print("  skipped:", s)


if __name__ == "__main__":
    asyncio.run(main())
