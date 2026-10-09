"""Bulk-generate questions for every subject of a grade through the normal
POST /generate endpoint, so all the usual checks apply (syllabus allow-list,
marks-aware answer rules, duplicate skipping, storage in the database).

Put this in backend/scripts/ and run it with the backend up on :8000.

    # preview the plan, sends nothing (works offline)
    python scripts/bulk_generate.py --dry-run

    # real run: 100 new Grade 9 questions per subject
    python scripts/bulk_generate.py --email you@school.in --password '...'
    python scripts/bulk_generate.py --token <JWT>          # or FIGURES_TOKEN-style env: GEN_TOKEN

    # 100 MORE per subject: re-run with a new seed
    python scripts/bulk_generate.py --token <JWT> --seed 2

    # only some subjects / a different size or grade
    python scripts/bulk_generate.py --token <JWT> --subjects Math Science --per-subject 50 --grade 9

    # also run "Verify answers" on everything that was generated
    python scripts/bulk_generate.py --token <JWT> --verify

Notes
- The account must be a Teacher/Admin (Students cannot generate).
- Every request sends refresh=true, so Groq writes fresh questions instead of
  returning stored ones. Exact-duplicate questions are skipped by the server, so
  a subject can come out slightly under the target; just re-run to top up.
- Requests are capped at the server's MAX_BATCH_COUNT (25) and paced to stay
  under the 30/min generate rate limit; 429s are retried after Retry-After.
- Needs httpx (pip install httpx).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

SYLLABUS = Path(__file__).resolve().parents[1] / "data" / "syllabus.json"
SUBJECTS = ["Math", "Science", "Social Science", "English", "Kannada"]
MAX_PER_REQUEST = 25

# Preferred exam-style mix (type, marks) -> weight. Combos the server does not
# support are dropped and the rest are renormalised.
MIX = {
    ("MCQ", 1): 35,
    ("Fill", 1): 10,
    ("Short", 1): 5,
    ("Short", 2): 15,
    ("Short", 3): 15,
    ("Match", 1): 5,
    ("Long", 5): 15,
}
FALLBACK_COMBOS = [("MCQ", 1), ("Short", 1), ("Short", 2), ("Short", 3), ("Long", 5)]


def log(msg: str) -> None:
    print(msg, flush=True)


def weighted_cycle(combos: list[tuple[str, int]], total: int) -> list[tuple[str, int]]:
    """A deterministic list of `total` combos in roughly MIX proportions."""
    weights = [MIX.get(c, 0) for c in combos]
    if not any(weights):
        weights = [1] * len(combos)
    scale = sum(weights)
    quotas = [round(total * w / scale) for w in weights]
    # fix rounding so the quotas add up to exactly `total`
    while sum(quotas) > total:
        quotas[quotas.index(max(quotas))] -= 1
    while sum(quotas) < total:
        quotas[quotas.index(max(quotas))] += 1
    # interleave proportionally so neighbouring slots use different combos
    keyed = []
    for combo, q in zip(combos, quotas):
        keyed.extend(((k + 0.5) / q, combo) for k in range(q))
    keyed.sort(key=lambda kc: kc[0])
    return [combo for _, combo in keyed]


def build_plan(chapters: list[str], combos: list[tuple[str, int]], total: int, seed: int = 42):
    """Spread `total` questions over chapters x combos, then group identical
    (chapter, type, marks) slots into batched requests. Difficulty is picked per
    request at random (seeded, so a re-run plans the same way) and is
    independent of the question type."""
    rng = random.Random(seed)
    slots = weighted_cycle(combos, total)
    counts: Counter = Counter()
    offset = seed % len(chapters)  # a different seed starts at a different chapter
    for q_type, marks in slots:
        chapter = chapters[offset % len(chapters)]
        offset += 1
        counts[(chapter, q_type, marks)] += 1
    jobs = []
    for (chapter, q_type, marks), n in counts.items():
        while n > 0:
            take = min(n, MAX_PER_REQUEST)
            diff = rng.choices(["easy", "medium", "hard"], weights=[3, 5, 2])[0]
            jobs.append(
                dict(chapter=chapter, type=q_type, marks=marks, difficulty=diff, count=take)
            )
            n -= take
    return jobs


def local_chapters(subject: str, grade: int) -> list[str]:
    data = json.loads(SYLLABUS.read_text(encoding="utf-8"))
    return list(data[subject]["grades"][str(grade)])


class Api:
    def __init__(self, base: str, token: str | None):
        self.client = httpx.Client(base_url=base, timeout=300)
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"

    def login(self, email: str, password: str) -> None:
        r = self.client.post("/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    def post(self, path: str, body: dict, tries: int = 4) -> httpx.Response:
        for attempt in range(1, tries + 1):
            r = self.client.post(path, json=body)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", "10")) + 1
                log(f"    rate limited, waiting {wait:.0f}s")
                time.sleep(wait)
                continue
            if r.status_code in (422, 502) and attempt < tries:
                log(f"    {r.status_code} from server, retrying ({attempt}/{tries - 1})")
                time.sleep(3)
                continue
            return r
        return r

    def get(self, path: str, **params) -> httpx.Response:
        return self.client.get(path, params=params)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--base-url", default=os.environ.get("API_URL", "http://localhost:8000/api/v1"),
                    help="include the API prefix (default http://localhost:8000/api/v1)")
    ap.add_argument("--token", default=os.environ.get("GEN_TOKEN"))
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--grade", type=int, default=9)
    ap.add_argument("--per-subject", type=int, default=100)
    ap.add_argument("--subjects", nargs="+", default=SUBJECTS, choices=SUBJECTS)
    ap.add_argument("--seed", type=int, default=42, help="change this on each re-run for a different plan")
    ap.add_argument("--figures", choices=["off", "mix", "all"], default="mix",
                    help="Science only (the only subject with a figure library): "
                         "mix = some questions about diagrams, all = every question about a diagram, off = theory only")
    ap.add_argument("--verify", action="store_true", help="run Verify answers on new questions")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, send nothing")
    args = ap.parse_args(argv)

    api = None
    combos = list(FALLBACK_COMBOS)
    if not args.dry_run:
        api = Api(args.base_url, args.token)
        if not args.token:
            if not (args.email and args.password):
                sys.exit("Give --token, or --email and --password.")
            api.login(args.email, args.password)
        r = api.get("/generation/combinations")
        r.raise_for_status()
        combos = [(c["type"], m) for c in r.json() for m in c["marks"]]
        log(f"Server supports: {combos}")

    grand_new = grand_cached = 0
    for subject in args.subjects:
        if api:
            r = api.get(f"/subjects/{subject}/chapters", grade=args.grade)
            r.raise_for_status()
            chapters = [c["name"] if isinstance(c, dict) else str(c) for c in r.json()]
        else:
            chapters = local_chapters(subject, args.grade)
        if not chapters:
            log(f"\n{subject}: no Grade {args.grade} chapters, skipping")
            continue

        jobs = build_plan(chapters, combos, args.per_subject, args.seed)
        log(f"\n== {subject} (Grade {args.grade}): {args.per_subject} questions, "
            f"{len(chapters)} chapters, {len(jobs)} requests ==")
        if args.dry_run:
            mix = Counter()
            for j in jobs:
                mix[(j["type"], j["marks"])] += j["count"]
            log(f"  mix: {dict(mix)}")
            for j in jobs[:5]:
                log(f"  e.g. {j}")
            continue

        new_ids: list[str] = []
        new = cached = failed = 0
        for n, job in enumerate(jobs, 1):
            body = dict(subject=subject, grade=args.grade, refresh=True, **job)
            if subject == "Science" and args.figures == "mix":
                body["mix_figures"] = True
            elif subject == "Science" and args.figures == "all":
                body["use_figures"] = True
            r = api.post("/generate", body)
            tag = f"[{n}/{len(jobs)}] {job['chapter'][:34]} {job['type']}/{job['marks']}m x{job['count']}"
            if r.status_code != 200:
                failed += job["count"]
                log(f"  {tag} -> {r.status_code} {r.text[:160]}")
                continue
            out = r.json()
            new += out.get("generated", 0)
            cached += out.get("cached", 0)
            new_ids += [q["id"] for q in out["questions"]]
            log(f"  {tag} -> +{out.get('generated', 0)} new")
            time.sleep(2.2)  # stay under 30 requests/min

        log(f"  {subject}: {new} new, {cached} reused, {failed} failed/skipped")
        grand_new += new
        grand_cached += cached

        if args.verify and new_ids:
            log(f"  verifying {len(new_ids)} answer keys...")
            for i in range(0, len(new_ids), 25):
                r = api.post("/questions/verify", {"question_ids": new_ids[i : i + 25]})
                if r.status_code == 200:
                    v = r.json()
                    log(f"    verified={v['verified']} unverified={v['unverified']} flagged={v['flagged']}")
                else:
                    log(f"    verify failed: {r.status_code} {r.text[:120]}")
                time.sleep(2.2)

        tot = api.get("/questions", subject=subject, grade=args.grade, page_size=1)
        if tot.status_code == 200:
            log(f"  bank now holds {tot.json()['total']} Grade {args.grade} {subject} questions")

    if not args.dry_run:
        log(f"\nDone. {grand_new} new questions added, {grand_cached} reused.")


if __name__ == "__main__":
    main()
