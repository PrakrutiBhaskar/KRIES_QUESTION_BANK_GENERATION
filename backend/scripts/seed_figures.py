"""Seed the figure library with the Grade 7 and Grade 8 Science diagrams.

Each grade folder (backend/data/figures/gradeN) holds the PNGs plus a manifest.json.
Every manifest entry is sent to the same POST /figures endpoint the admin UI uses, so the
database, the stored files and any object-storage upload follow the normal path.

Re-running is safe: a figure whose (chapter, caption) already exists is skipped.

Usage (backend running on :8000, admin token copied from the browser's Authorization header):

    python scripts/seed_figures.py --token <ADMIN_JWT>                 # grades 7 and 8
    python scripts/seed_figures.py --token <ADMIN_JWT> --grades 8      # only grade 8
    python scripts/seed_figures.py --dry-run                           # list, send nothing

The token can also come from the FIGURES_TOKEN environment variable.
Needs httpx (pip install httpx), which the test suite already uses.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

FIGURES_DIR = Path(__file__).resolve().parents[1] / "data" / "figures"


def load_manifest(grade: int) -> tuple[Path, list[dict]]:
    folder = FIGURES_DIR / f"grade{grade}"
    manifest = folder / "manifest.json"
    if not manifest.exists():
        sys.exit(f"No manifest at {manifest}")
    entries = json.loads(manifest.read_text(encoding="utf-8"))["figures"]
    for e in entries:
        if not (folder / e["file"]).exists():
            sys.exit(f"grade{grade}: {e['file']} is listed in the manifest but missing on disk")
    return folder, entries


def existing_keys(client: httpx.Client, subject: str) -> set[tuple[str, str]]:
    """(chapter, caption) of every figure already in the library for this subject."""
    keys: set[tuple[str, str]] = set()
    page = 1
    while True:
        r = client.get("/figures", params={"subject": subject, "page": page, "page_size": 100})
        r.raise_for_status()
        body = r.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        for it in items:
            keys.add((it.get("chapter", ""), it.get("caption", "")))
        total = body.get("total", len(items)) if isinstance(body, dict) else len(items)
        if not items or page * 100 >= total:
            return keys
        page += 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--token", default=os.environ.get("FIGURES_TOKEN"), help="admin bearer token")
    ap.add_argument("--grades", nargs="+", type=int, default=[7, 8])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan = []  # (grade, folder, entry)
    for g in args.grades:
        folder, entries = load_manifest(g)
        plan += [(g, folder, e) for e in entries]
    print(f"{len(plan)} figures in the manifests for grade(s) {args.grades}")

    if args.dry_run:
        for g, _, e in plan:
            print(f"  grade {g}  {e['chapter']}  |  {e['file']}")
        return
    if not args.token:
        sys.exit("Pass --token (or set FIGURES_TOKEN) with an admin token.")

    with httpx.Client(base_url=args.base_url, headers={"Authorization": f"Bearer {args.token}"}, timeout=60) as client:
        have = existing_keys(client, "Science")
        added = skipped = failed = 0
        for g, folder, e in plan:
            if (e["chapter"], e["caption"]) in have:
                skipped += 1
                continue
            r = client.post(
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
            if r.status_code == 201:
                added += 1
            else:
                failed += 1
                print(f"  FAILED grade {g} {e['file']}: {r.status_code} {r.text[:200]}")
        print(f"added {added}, already present {skipped}, failed {failed}")
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
