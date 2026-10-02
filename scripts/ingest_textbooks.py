#!/usr/bin/env python3
"""
Ingest KTBS textbook PDFs into the textbook corpus the generator writes from.

Put the official Karnataka Textbook Society PDFs (text-layer, not scans) in one
folder, named  <subject>_<grade>[_<part>].pdf :

    math_7_1.pdf  math_7_2.pdf  science_8.pdf  social-science_9_1.pdf
    social-science_9_2.pdf  english_7.pdf  kannada_8.pdf

Subjects: math, science, social-science (or social_science), english, kannada.
Grades: 7, 8, 9.  Optional trailing number = book part (Maths Part 1/2, ...).

    python scripts/ingest_textbooks.py pdfs/                 # dry run, prints a report
    python scripts/ingest_textbooks.py pdfs/ --write         # writes backend/data/textbooks/*.json
    python scripts/ingest_textbooks.py pdfs/ --write --medium Kannada
    python scripts/ingest_textbooks.py one.pdf --subject Science --grade 8 --write
    python scripts/ingest_textbooks.py one.pdf --subject Science --grade 8 \
        --chapters-file chapters.txt --write     # explicit titles, one per line

Always read the dry-run report first: it lists the chapters found per book,
passage counts, and anything suspicious (chapters not located, a non-Unicode
Kannada text layer, chapters with almost no text). Exit code is 1 if any book
failed or produced zero chapters.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generation_engine import Subject  # noqa: E402
from generation_engine.textbook_ingest import ingest_pdf  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "backend" / "data" / "textbooks"
_NAME = re.compile(r"^(?P<subject>[a-z_\- ]+?)[_\- ](?P<grade>\d{1,2})(?:[_\- ](?:part)?(?P<part>\d))?$", re.I)
_SUBJECTS = {s.value.lower().replace(" ", "-"): s for s in Subject}
_SUBJECTS.update({s.value.lower().replace(" ", "_"): s for s in Subject})


def parse_name(path: Path):
    m = _NAME.match(path.stem)
    if not m:
        return None
    subject = _SUBJECTS.get(m.group("subject").lower().strip())
    grade = int(m.group("grade"))
    if subject is None or grade not in (7, 8, 9):
        return None
    return subject, grade, m.group("part") or ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path, help="A PDF, or a folder of PDFs named <subject>_<grade>[_<part>].pdf")
    ap.add_argument("--subject", choices=[s.value for s in Subject], help="Single-PDF mode")
    ap.add_argument("--grade", type=int, choices=[7, 8, 9], help="Single-PDF mode")
    ap.add_argument("--part", default="", help="Single-PDF mode: book part, e.g. 1")
    ap.add_argument("--medium", default="English", help="Textbook medium label (default English)")
    ap.add_argument("--chapters-file", type=Path, help="Explicit chapter titles, one per line (overrides detection)")
    ap.add_argument("--target-chars", type=int, default=900, help="Approx passage size (default 900)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"Output folder (default {DEFAULT_OUT})")
    ap.add_argument("--write", action="store_true", help="Write corpus files (default: dry run)")
    args = ap.parse_args()

    jobs: list[tuple[Path, Subject, int, str]] = []
    if args.path.is_dir():
        for pdf in sorted(args.path.glob("*.pdf")):
            parsed = parse_name(pdf)
            if parsed is None:
                print(f"skip   {pdf.name}: name must look like science_8.pdf / math_7_1.pdf", file=sys.stderr)
                continue
            jobs.append((pdf, *parsed))
    else:
        if not args.subject or not args.grade:
            print("error: single-PDF mode needs --subject and --grade", file=sys.stderr)
            return 1
        jobs.append((args.path, Subject(args.subject), args.grade, args.part))

    if not jobs:
        print("error: no PDFs to ingest", file=sys.stderr)
        return 1

    chapters = None
    if args.chapters_file:
        chapters = [l.strip() for l in args.chapters_file.read_text(encoding="utf-8").splitlines() if l.strip()]

    failed = 0
    for pdf, subject, grade, part in jobs:
        label = f"{subject.value} Class {grade}" + (f" part {part}" if part else "")
        try:
            result = ingest_pdf(
                pdf, subject, grade, part, args.medium,
                chapters=chapters, target_chars=args.target_chars,
            )
        except (ValueError, FileNotFoundError, ImportError) as exc:
            print(f"FAIL   {label} ({pdf.name}): {exc}")
            failed += 1
            continue
        print(f"OK     {label} ({pdf.name}): {result.chapters_found} chapters, "
              f"{result.passages} passages via {result.method}")
        for ch in result.corpus["chapters"]:
            print(f"         {ch['number']:>2}. {ch['title']}  [{len(ch['passages'])} passages]")
        for w in result.warnings:
            print(f"       ! {w}")
        if result.chapters_found == 0:
            failed += 1
            continue
        if args.write:
            args.out.mkdir(parents=True, exist_ok=True)
            fname = f"{subject.value.lower().replace(' ', '-')}_{grade}" + (f"_{part}" if part else "") + ".json"
            (args.out / fname).write_text(json.dumps(result.corpus, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"       wrote {args.out / fname}")

    if not args.write:
        print("\nDry run — nothing written. Re-run with --write once the report looks right.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
