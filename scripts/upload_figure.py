"""
Bulk-add diagrams to the figure library from the server.

Administrators can do the same one image at a time from the Figure Library page
in the web app; this script is for loading a folder of images at once. It writes
straight into the database and FIGURE_DIR, and every image goes through the same
checks as a web upload (real image decoding, flattened onto white, metadata
stripped, scaled for print).

The library is shared: once added, every teacher can write questions about a
figure and attach it, and its diagram is printed in the answer key.

A figure needs a caption or labels, and a subject and chapter, to be picked up by
"Write questions about figures" for that chapter. --admin must be the email of an
account with the Admin role (see scripts/make_admin.py); it is recorded as the
uploader.

Examples:
    python scripts/upload_figure.py cell.png --admin principal@school.in \\
        --subject Science --chapter "Cell - Structure and Functions" \\
        --caption "Plant cell" --labels "A: nucleus" "B: cell wall" "C: chloroplast"

    # Several images, same chapter
    python scripts/upload_figure.py a.png b.png --admin principal@school.in \\
        --subject Science --chapter Photosynthesis --caption "Leaf diagram"

    # A whole folder, each image with its own caption / chapter / labels
    python scripts/upload_figure.py --manifest backend/data/figures/manifest.json \\
        --admin principal@school.in --dry-run      # check first, writes nothing
    python scripts/upload_figure.py --manifest backend/data/figures/manifest.json \\
        --admin principal@school.in

The manifest is JSON: {"figures": [{"file": "cell.png", "subject": "Science",
"chapter": "...", "topic": "...", "caption": "...", "labels": ["..."]}, ...]}.
`file` is relative to the manifest. Running it again skips figures already in
the library with the same subject, chapter and caption (use --force to add anyway).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.db import build_engine  # noqa: E402
from app.errors import BadRequestError, PayloadTooLargeError  # noqa: E402
from app.services import auth as auth_service  # noqa: E402
from app.services import figures as figure_service  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Add diagrams to the figure library.")
    ap.add_argument("files", nargs="*", type=Path, help="PNG / JPEG / GIF / WebP file(s)")
    ap.add_argument(
        "--manifest", type=Path, help="JSON file giving each image its own metadata (bulk mode)"
    )
    ap.add_argument("--dry-run", action="store_true", help="Validate everything, write nothing")
    ap.add_argument(
        "--force", action="store_true", help="Add figures even if the same caption already exists"
    )
    ap.add_argument("--admin", required=True, help="Email of an administrator account (the uploader)")
    ap.add_argument("--subject", default="", help="Science, Math or Social Science")
    ap.add_argument("--chapter", default="", help="Chapter name, as in the syllabus")
    ap.add_argument("--topic", default="", help="Optional topic within the chapter")
    ap.add_argument("--caption", default="", help="What the diagram shows (printed under it)")
    ap.add_argument(
        "--labels", nargs="*", default=[], help='Labelled parts, e.g. "A: nucleus" "B: cell wall"'
    )
    args = ap.parse_args(argv)
    if not args.files and not args.manifest:
        ap.error("give at least one image file, or --manifest")
    return args


def load_jobs(args: argparse.Namespace) -> list[dict]:
    """One dict per image: path plus its caption / subject / chapter / topic / labels."""
    jobs: list[dict] = []
    for path in args.files:
        jobs.append(
            {
                "path": path,
                "caption": args.caption,
                "subject": args.subject,
                "chapter": args.chapter,
                "topic": args.topic,
                "labels": args.labels,
            }
        )
    if args.manifest:
        base = args.manifest.resolve().parent
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        entries = data["figures"] if isinstance(data, dict) else data
        for entry in entries:
            jobs.append(
                {
                    "path": base / entry["file"],
                    "caption": entry.get("caption", args.caption),
                    "subject": entry.get("subject", args.subject),
                    "chapter": entry.get("chapter", args.chapter),
                    "topic": entry.get("topic", args.topic),
                    "labels": entry.get("labels", args.labels),
                }
            )
    return jobs


def _key(subject: str, chapter: str, caption: str) -> tuple[str, str, str]:
    norm = lambda v: " ".join((v or "").split()).lower()  # noqa: E731
    return norm(subject), norm(chapter), norm(caption)


async def run(args: argparse.Namespace) -> int:
    engine = build_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    failures = 0
    try:
        async with factory() as session:
            admin = await auth_service.get_by_email(session, args.admin.strip().lower())
            if admin is None:
                print(f"No account with email {args.admin!r}. Sign up in the app first.")
                return 2
            if admin.role != "Admin":
                print(f"{args.admin!r} is not an administrator. Run scripts/make_admin.py first.")
                return 2
            existing = {
                _key(f.subject or "", f.chapter or "", f.caption or "")
                for f in (await figure_service.list_figures(session, limit=100000))[0]
            }
            admin_id = admin.id  # rollback() expires ORM objects; keep the plain value
            jobs = load_jobs(args)
            added = skipped = 0
            for job in jobs:
                path: Path = job["path"]
                key = _key(job["subject"], job["chapter"], job["caption"])
                if key in existing and not args.force:
                    skipped += 1
                    print(f"exists  {path.name}: same subject/chapter/caption already in the library")
                    continue
                try:
                    kwargs = {k: job[k] for k in ("caption", "subject", "chapter", "topic", "labels")}
                    figure = await figure_service.create_figure(
                        session, path.read_bytes(), uploaded_by=admin_id, **kwargs
                    )
                    if args.dry_run:
                        stored = figure_service.figure_path(figure)  # read before rollback
                        await session.rollback()
                        stored.unlink(missing_ok=True)
                        print(f"ok      {path.name}")
                    else:
                        await session.commit()
                        print(f"added   {path.name}: figure {figure.id}")
                    existing.add(key)
                    added += 1
                except (BadRequestError, PayloadTooLargeError) as exc:
                    await session.rollback()
                    failures += 1
                    print(f"skipped {path.name}: {exc.detail}")
                except OSError as exc:
                    failures += 1
                    print(f"skipped {path}: {exc}")
            verb = "would add" if args.dry_run else "added"
            print(f"\n{verb} {added}, already present {skipped}, failed {failures}")
    finally:
        await engine.dispose()
    return 1 if failures else 0


def main() -> None:
    sys.exit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
