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
"""
from __future__ import annotations

import argparse
import asyncio
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
    ap.add_argument("files", nargs="+", type=Path, help="PNG / JPEG / GIF / WebP file(s)")
    ap.add_argument("--admin", required=True, help="Email of an administrator account (the uploader)")
    ap.add_argument("--subject", default="", help="Science, Math or Social Science")
    ap.add_argument("--chapter", default="", help="Chapter name, as in the syllabus")
    ap.add_argument("--topic", default="", help="Optional topic within the chapter")
    ap.add_argument("--caption", default="", help="What the diagram shows (printed under it)")
    ap.add_argument(
        "--labels", nargs="*", default=[], help='Labelled parts, e.g. "A: nucleus" "B: cell wall"'
    )
    return ap.parse_args(argv)


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
            for path in args.files:
                try:
                    figure = await figure_service.create_figure(
                        session,
                        path.read_bytes(),
                        caption=args.caption,
                        uploaded_by=admin.id,
                        subject=args.subject,
                        chapter=args.chapter,
                        topic=args.topic,
                        labels=args.labels,
                    )
                    await session.commit()
                    print(f"added {path.name}: figure {figure.id}")
                except (BadRequestError, PayloadTooLargeError) as exc:
                    await session.rollback()
                    failures += 1
                    print(f"skipped {path.name}: {exc.detail}")
                except OSError as exc:
                    failures += 1
                    print(f"skipped {path}: {exc}")
    finally:
        await engine.dispose()
    return 1 if failures else 0


def main() -> None:
    sys.exit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
