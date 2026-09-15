"""
Difficulty tagging.

Primary path: difficulty is prompted for directly (see prompts.py) and
assigned straight onto the Question from the GenerationRequest — this is
what "difficulty tagging" means for the MVP (spec.md Module A bullet list:
"Difficulty tagging (easy/medium/hard) — prompted directly or scored
post-generation").

Secondary path: `estimate_difficulty` is a lightweight heuristic scorer that
can be used as a sanity cross-check against the prompted value (e.g. flag
for review if a "hard" question scores as trivially easy), without adding a
second LLM call for every item.
"""
from __future__ import annotations

import re

from .schemas import Difficulty, Question

_COMPLEXITY_WORDS = re.compile(
    r"\b(derive|analy[sz]e|evaluate|justify|compare|contrast|explain why|"
    r"prove|synthes[ei]ze|critici[sz]e|hence|therefore)\b",
    re.IGNORECASE,
)


def estimate_difficulty(question: Question) -> Difficulty:
    """
    Rough heuristic: longer answers with more "higher-order" verbs and more
    distinct points score as harder. This is a coarse cross-check, not a
    replacement for the prompted difficulty — use it to flag mismatches
    for human review rather than to silently override the requested value.
    """
    text = f"{question.text} {question.answer}"
    word_count = len(text.split())
    complexity_hits = len(_COMPLEXITY_WORDS.findall(text))

    score = 0
    score += min(word_count // 20, 4)  # length signal, capped
    score += complexity_hits
    score += {1: 0, 2: 1, 3: 2, 5: 3}.get(question.marks, 0)

    if score <= 2:
        return Difficulty.EASY
    if score <= 5:
        return Difficulty.MEDIUM
    return Difficulty.HARD


def flag_difficulty_mismatch(question: Question) -> str | None:
    """
    Returns a warning string if the heuristic estimate disagrees sharply
    with the prompted difficulty (easy vs. hard, in either direction), else
    None. Medium is treated as adjacent to both, so it never triggers a flag.
    """
    estimated = estimate_difficulty(question)
    requested = question.difficulty
    sharp_mismatch = {Difficulty.EASY, Difficulty.HARD} == {estimated, requested}
    if sharp_mismatch:
        return (
            f"requested difficulty '{requested.value}' but heuristic scorer "
            f"estimates '{estimated.value}' — consider human review"
        )
    return None
