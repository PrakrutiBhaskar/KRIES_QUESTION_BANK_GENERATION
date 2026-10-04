"""
Why aren't my diagram questions / answer-key diagrams showing up?

Checks every figure in the library against the two things that must be true for
it to be used, and reports the ones that fail:

  1. Its subject + chapter must match a chapter in the current syllabus. The
     "diagram-based questions" lookup (Generate page and blueprint papers) is an
     exact chapter-name match, so a figure tagged with a retired chapter name is
     never picked, and the paper quietly comes out theory-only.
  2. Its image file must exist in FIGURE_DIR. A missing file is skipped when a
     PDF is exported, so the diagram vanishes from the paper and the answer key
     (this happens when the database survives but the disk does not, e.g. a
     redeploy on a host with no persistent volume).

It is read-only unless you pass --apply, which retags figures using a chapter map
(default backend/data/figures/chapter_map.json: old chapter -> current chapter).

    python scripts/check_figures.py                 # report only
    python scripts/check_figures.py --apply         # retag what the map covers
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import build_engine  # noqa: E402
from app.models import Figure  # noqa: E402
from app.services import figures as figure_service  # noqa: E402

DEFAULT_SYLLABUS = ROOT / "backend" / "data" / "syllabus.json"
DEFAULT_MAP = ROOT / "backend" / "data" / "figures" / "chapter_map.json"


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def syllabus_chapters(path: Path) -> dict[str, set[str]]:
    """subject -> normalised chapter names that exist in the syllabus (any grade)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for subject, entry in data.items():
        if subject.startswith("_") or not isinstance(entry, dict):
            continue
        names = list(entry.get("chapters", []))
        for chapters in (entry.get("grades") or {}).values():
            names.extend(chapters)
        out[subject] = {norm(c) for c in names}
    return out


def load_map(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        subj: {norm(old): new for old, new in m.items()}
        for subj, m in raw.items()
        if not subj.startswith("_") and isinstance(m, dict)
    }


async def run(args: argparse.Namespace) -> int:
    known = syllabus_chapters(args.syllabus)
    chapter_map = load_map(args.map)
    engine = build_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            figures = list((await session.scalars(select(Figure))).all())
            print(f"FIGURE_DIR: {settings.figure_dir}")
            print(f"{len(figures)} figure(s) in the library\n")

            untagged = [f for f in figures if not (f.subject and f.chapter)]
            no_text = [f for f in figures if not figure_service.has_metadata(f)]
            missing = [f for f in figures if not figure_service.figure_path(f).exists()]
            orphan = [
                f for f in figures
                if f.subject and f.chapter and norm(f.chapter) not in known.get(f.subject, set())
            ]
            usable = [f for f in figures if f not in untagged and f not in orphan and f not in no_text]

            print(f"usable for diagram questions : {len(usable)}")
            print(f"tagged with a chapter that is not in the syllabus : {len(orphan)}")
            print(f"no subject/chapter tag (never picked automatically): {len(untagged)}")
            print(f"no caption or labels (nothing to write from)       : {len(no_text)}")
            print(f"image file missing from FIGURE_DIR (not printed)   : {len(missing)}\n")

            if orphan:
                print("Chapters in the library that the syllabus does not have:")
                counts = Counter((f.subject, f.chapter) for f in orphan)
                for (subj, ch), n in sorted(counts.items()):
                    target = chapter_map.get(subj, {}).get(norm(ch))
                    print(f"  {subj} / {ch}: {n} figure(s)  ->  {target or 'no mapping (retag by hand)'}")
                print()
            if missing:
                print("Missing files (re-upload these, or restore FIGURE_DIR from a backup):")
                for f in missing[:40]:
                    print(f"  {f.id}  {f.caption[:70]!r}  [{f.filename}]")
                if len(missing) > 40:
                    print(f"  ... and {len(missing) - 40} more")
                print()

            changes = [
                (f, chapter_map[f.subject][norm(f.chapter)])
                for f in orphan
                if norm(f.chapter) in chapter_map.get(f.subject, {})
            ]
            if not changes:
                print("Nothing the chapter map can retag.")
                return 0
            if not args.apply:
                print(f"Would retag {len(changes)} figure(s). Re-run with --apply to do it.")
                return 0
            for f, new in changes:
                f.chapter = new
            await session.commit()
            print(f"Retagged {len(changes)} figure(s).")
    finally:
        await engine.dispose()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="retag figures the chapter map covers")
    ap.add_argument("--syllabus", type=Path, default=DEFAULT_SYLLABUS)
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
    sys.exit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
