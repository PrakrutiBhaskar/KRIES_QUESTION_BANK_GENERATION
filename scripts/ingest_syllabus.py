#!/usr/bin/env python3
"""
Syllabus PDF-ingestion CLI.

Extracts chapter titles from a textbook PDF's table of contents and merges
them into backend/data/syllabus.json (or wherever --out points). This is the
tool referenced by generation_engine/syllabus_ingest.py's module docstring
and by docs/task-tracker.md's "syllabus ingestion" item.

Defaults to a dry run: it always prints what it found first, and only writes
to disk when you pass --write. Textbook contents pages aren't uniform enough
to trust blind — review the printed list before committing it.

Examples:
    # Preview only — find the right --pages range first. Point this at a
    # generous guess (the first ~10 pages) to see where the real contents
    # page landed, then narrow it down in the next run.
    python scripts/ingest_syllabus.py science_grade8.pdf --subject Science --pages 1-10

    # Once you've found the actual TOC page range, ingest for real
    python scripts/ingest_syllabus.py science_grade8.pdf --subject Science --pages 4-5 --write

    # Add more chapters to a subject that already has some (default mode)
    python scripts/ingest_syllabus.py science_grade9.pdf --subject Science --pages 3-4 --write

    # Start a subject's chapter list over from scratch instead of appending
    python scripts/ingest_syllabus.py math_grade7.pdf --subject Math --pages 2-3 --write --mode replace

Exit code is 0 only if at least one chapter was extracted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generation_engine import Subject  # noqa: E402
from generation_engine.syllabus_ingest import (  # noqa: E402
    extract_chapters_from_pdf,
    merge_chapters,
)

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "backend" / "data" / "syllabus.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf_path", type=Path, help="Path to the textbook PDF")
    parser.add_argument(
        "--subject",
        required=True,
        choices=[s.value for s in Subject],
        help="Which subject these chapters belong to",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help=(
            "1-indexed, inclusive page range to scan, e.g. '4-5' or '4'. "
            "Omit to scan the whole PDF (noisier — see the module docstring "
            "in generation_engine/syllabus_ingest.py for why)."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"syllabus.json to merge into (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--mode",
        choices=["append", "replace"],
        default="append",
        help="append (default): add to this subject's existing chapters, "
        "deduped. replace: discard this subject's existing chapters first.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write --out. Without this flag, only prints a preview.",
    )
    args = parser.parse_args()

    subject = Subject(args.subject)

    try:
        chapters = extract_chapters_from_pdf(args.pdf_path, pages=args.pages)
    except FileNotFoundError:
        print(f"error: {args.pdf_path} not found", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not chapters:
        print(
            "No chapter-shaped lines found in that page range.\n"
            "Try a different --pages range, or check the PDF actually has "
            "a text layer (pdffonts/pdftotext, or generation_engine/syllabus_ingest.py's "
            "docstring for what this pipeline does and doesn't handle).",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(chapters)} chapter-shaped line(s) for {subject.value}:\n")
    for i, title in enumerate(chapters, start=1):
        print(f"  {i:2}. {title}")
    print()

    if not args.write:
        print("Dry run — nothing written. Re-run with --write once this list looks right.")
        return 0

    existing: dict = {}
    if args.out.exists():
        with open(args.out, "r", encoding="utf-8") as fh:
            existing = json.load(fh)

    updated, added, skipped = merge_chapters(existing, subject, chapters, mode=args.mode)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(updated, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(
        f"Wrote {args.out} — {added} new chapter(s) added, "
        f"{skipped} already present and skipped "
        f"({subject.value} now has {len(updated[subject.value]['chapters'])} total)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
