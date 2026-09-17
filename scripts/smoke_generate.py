#!/usr/bin/env python3
"""
Live smoke test — hits the real Groq API and prints what comes back.

This is the manual counterpart to the offline test suite: `pytest` proves the
logic is correct, this proves the prompts actually produce usable questions
from a real model. Needs GROQ_API_KEY set (in .env or the environment).

Examples:
    python scripts/smoke_generate.py
    python scripts/smoke_generate.py --subject Math --chapter "Linear Equations" --type Short --marks 3 --count 5
    python scripts/smoke_generate.py --all-combos --subject Science --chapter "Force and Pressure"
    python scripts/smoke_generate.py --all-subjects --json

Exit code is 0 only if every requested batch generated successfully.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generation_engine import (  # noqa: E402
    Difficulty,
    GenerationEngine,
    GenerationRequest,
    GenerationValidationError,
    GroqAPIError,
    GroqClient,
    InvalidRequestError,
    QuestionType,
    Subject,
    VALID_GRADES,
    settings,
)
from generation_engine.prompts import supported_combinations  # noqa: E402

DEFAULT_CHAPTERS = {
    Subject.SCIENCE: "Nutrition in Plants",
    Subject.MATH: "Linear Equations in One Variable",
    Subject.SOCIAL_SCIENCE: "The Indian Constitution",
    Subject.ENGLISH: "Tenses and Sentence Structure",
    Subject.KANNADA: "Vyakarana",
}

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[2m",
    "\033[0m",
)


def print_question(i, q):
    print(f"\n  {DIM}[{i}]{RESET} {q.text}")
    if q.options:
        for opt in q.options:
            marker = "*" if opt.strip() == q.answer.strip() else " "
            print(f"      {marker} {opt}")
    else:
        for line in q.answer.splitlines():
            print(f"      {line}")
    if q.explanation:
        print(f"      {DIM}why: {q.explanation}{RESET}")
    print(f"      {DIM}topic: {q.topic or '-'} | tags: {', '.join(q.tags) or '-'}{RESET}")


async def run_one(engine, request, as_json):
    label = (
        f"{request.subject.value} / {request.chapter} / "
        f"{request.type.value} / {request.marks}m / grade {request.grade} / "
        f"{request.difficulty.value} / n={request.count}"
    )
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")

    started = time.monotonic()
    try:
        questions, report = await engine.generate(request)
    except InvalidRequestError as e:
        print(f"{RED}400 invalid request:{RESET} {e.detail}")
        return False
    except GroqAPIError as e:
        print(f"{RED}502 Groq failure:{RESET} {e.detail}")
        return False
    except GenerationValidationError as e:
        print(f"{RED}422 validation failed:{RESET} {e.detail}")
        for reason in e.context.get("report", {}).get("rejection_reasons", [])[:8]:
            print(f"    {DIM}- {reason}{RESET}")
        return False
    elapsed = time.monotonic() - started

    if as_json:
        print(json.dumps([q.model_dump(mode="json") for q in questions], indent=2,
                         ensure_ascii=False))
    else:
        for i, q in enumerate(questions, 1):
            print_question(i, q)

    print(
        f"\n{GREEN}OK{RESET} {len(questions)}/{request.count} in {elapsed:.1f}s "
        f"({report.attempts} attempt(s))"
    )
    dropped = (
        report.dropped_schema_invalid
        + report.dropped_marks_format_invalid
        + report.dropped_duplicates
        + report.dropped_irrelevant
    )
    if dropped:
        print(
            f"{YELLOW}dropped{RESET} {report.dropped_schema_invalid} schema, "
            f"{report.dropped_marks_format_invalid} marks-format, "
            f"{report.dropped_duplicates} duplicate, "
            f"{report.dropped_irrelevant} irrelevant"
        )
        for reason in report.rejection_reasons[:5]:
            print(f"    {DIM}- {reason}{RESET}")
    for warning in report.difficulty_warnings:
        print(f"{YELLOW}difficulty{RESET} {warning}")

    # test-plan.md Section 1: batch must contain no duplicates
    texts = [q.text.strip().lower() for q in questions]
    if len(set(texts)) != len(texts):
        print(f"{RED}FAIL{RESET} duplicate question text survived into the batch")
        return False
    return True


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", default="Science",
                        choices=[s.value for s in Subject])
    parser.add_argument("--chapter")
    parser.add_argument("--type", default="MCQ",
                        choices=[t.value for t in QuestionType])
    parser.add_argument("--marks", type=int, default=1)
    parser.add_argument("--grade", type=int, default=8,
                        help="target grade, 7-9 (default: 8)")
    parser.add_argument("--difficulty", default="medium",
                        choices=[d.value for d in Difficulty])
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--topic")
    parser.add_argument("--all-combos", action="store_true",
                        help="run every supported (type, marks) pair")
    parser.add_argument("--all-subjects", action="store_true",
                        help="run one batch per subject")
    parser.add_argument("--json", action="store_true",
                        help="dump raw Question JSON instead of formatted output")
    parser.add_argument("--batch-delay", type=float, default=3.0,
                        help="seconds to sleep between batches when running "
                             "--all-combos/--all-subjects, to stay clear of "
                             "the Groq tokens-per-minute limit (default: 3.0)")
    parser.add_argument("--max-retries", type=int, default=None,
                        help="Groq transport-level retries per call. "
                             "Defaults to settings.groq_max_retries normally, "
                             "or 5 for --all-combos/--all-subjects runs, "
                             "which are more likely to hit the TPM ceiling "
                             "and need a longer runway to recover.")
    args = parser.parse_args()

    if args.grade not in VALID_GRADES:
        print(f"{RED}--grade must be one of {sorted(VALID_GRADES)}, got "
              f"{args.grade}.{RESET}")
        return 1

    if not settings.groq_api_key:
        print(f"{RED}GROQ_API_KEY is not set.{RESET} Add it to .env or export it.")
        return 1

    print(f"{DIM}model: {settings.groq_model} | temp: {settings.groq_temperature} | "
          f"retries: {settings.max_regeneration_retries}{RESET}")

    subjects = list(Subject) if args.all_subjects else [Subject(args.subject)]
    combos = (
        supported_combinations()
        if args.all_combos
        else [(QuestionType(args.type), args.marks)]
    )

    multi_batch = args.all_combos or args.all_subjects
    max_retries = args.max_retries
    if max_retries is None:
        max_retries = 5 if multi_batch else settings.groq_max_retries

    engine = GenerationEngine(groq_client=GroqClient(max_retries=max_retries))
    results = []
    for subject in subjects:
        chapter = args.chapter or DEFAULT_CHAPTERS[subject]
        for qtype, marks in combos:
            if multi_batch and results:
                # Space batches out so we don't repeatedly slam into Groq's
                # tokens-per-minute limit and burn the whole retry budget.
                await asyncio.sleep(args.batch_delay)
            request = GenerationRequest(
                subject=subject, chapter=chapter, type=qtype, grade=args.grade,
                marks=marks, difficulty=Difficulty(args.difficulty),
                count=args.count, topic=args.topic,
            )
            results.append(await run_one(engine, request, args.json))

    passed = sum(results)
    print(f"\n{'=' * 78}")
    colour = GREEN if passed == len(results) else RED
    print(f"{colour}{passed}/{len(results)} batches generated successfully{RESET}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
