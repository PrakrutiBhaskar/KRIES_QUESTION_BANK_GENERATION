"""
Answer-key verification: rule checks first, then an independent AI pass.

Why: the model that writes a question also writes its answer key, and a wrong
key is the worst failure an exam-paper tool can have, because it looks
authoritative. Two defences, cheapest first:

  1. rule_checks.py computes or looks up the answer for the patterns it can be
     certain about (arithmetic, SI units, physics formulas...). Free, exact.
  2. Anything the rules can't decide goes to a second Groq call that checks
     the key *independently*:
       - MCQ: the verifier is NOT shown the key. It solves the question itself
         and picks an option, and we compare with the key. Showing the key
         would invite it to agree.
       - Short / Long: there is nothing to compare mechanically, so the
         verifier is shown the answer and asked to check it sceptically.
     One call per chunk of questions, not one per question.

Each question ends in one of three states:

  verified    a rule confirmed the key, or the AI pass reached the same answer
  unverified  nothing could be checked (no rule applies, the AI pass was not
              confident, or it failed). Kept: the key is merely unconfirmed.
  rejected    a rule or the AI pass found the key wrong. The engine reports it
              as "flagged" (see GenerationEngine.verify_answers); the teacher
              decides whether to regenerate or delete it.

Verification runs on demand (the "Verify answers" button), not during
generation, so generating questions never waits for it.

The AI pass fails open: a Groq error means "unverified", never a failed
request. Rule hits are final (no AI pass is spent on a question a rule already
decided).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .exceptions import GroqAPIError
from .rule_checks import NOT_APPLICABLE, RuleResult, check_answer_rules
from .schemas import Question, QuestionType

logger = logging.getLogger("generation_engine.verification")

VERIFIED = "verified"
UNVERIFIED = "unverified"
REJECTED = "rejected"  # engine-internal: reported as "flagged"
FLAGGED = "flagged"

_LETTERS = "ABCD"
_LETTERS_ALL = "ABCDEFGHIJ"  # Match columns can have up to five options
_NOTE_LIMIT = 280

VERIFIER_SYSTEM_PROMPT = (
    "You are an independent answer-key verifier for school exam questions. "
    "You work each problem out yourself, carefully, and never assume the "
    "answer you are shown or the first option is correct. You reply with "
    "JSON only."
)


@dataclass(frozen=True)
class Verification:
    status: str  # VERIFIED | UNVERIFIED | REJECTED
    note: str


@dataclass(frozen=True)
class LlmVerdict:
    outcome: str  # "agree" | "disagree" | "uncertain"
    detail: str = ""


def _trim(text: str, limit: int = _NOTE_LIMIT) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# The AI pass
# ---------------------------------------------------------------------------


def _context_line(questions: list[Question]) -> str:
    first = questions[0]
    return (
        f"Subject: {first.subject.value}. Karnataka State Board Class {first.grade}. "
        f'Chapter: "{first.chapter}".'
    )


_FIGURE_NOTE = (
    'Items with a "figure" field refer to a diagram printed beside the question. '
    "You cannot see it: the field is a text description of it (caption and labelled "
    "parts) and is the ground truth about the diagram. Judge the answer against that "
    "description and the subject. If answering needs detail the description does not "
    "give, treat the item as uncertain rather than guessing.\n\n"
)


def _figure_note(questions: list[Question]) -> str:
    return _FIGURE_NOTE if any(q.figure_context for q in questions) else ""


def _with_figure(item: dict, q: Question) -> dict:
    """Add the figure description to a verifier item (omitted when there is none)."""
    if q.figure_context:
        item["figure"] = q.figure_context
    return item


def build_mcq_prompt(questions: list[Question]) -> tuple[str, str]:
    items = [
        _with_figure(
            {
                "index": i,
                "question": q.text,
                "options": {_LETTERS[j]: opt for j, opt in enumerate(q.options or [])},
            },
            q,
        )
        for i, q in enumerate(questions)
    ]
    user = (
        f"{_context_line(questions)}\n\n{_figure_note(questions)}"
        "Solve each multiple-choice question below yourself and choose the single "
        "best option. Work it out first (do the calculation, recall the fact) "
        "before choosing. If two options could both be argued correct, or none "
        'is correct, set "confidence" to "low".\n\n'
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        'Return ONLY a JSON object: {"results": [{"index": 0, "choice": "A", '
        '"confidence": "high" | "medium" | "low", "reasoning": "one short sentence"}, ...]} '
        "with exactly one entry per question and no other text."
    )
    return VERIFIER_SYSTEM_PROMPT, user


_MATCH_NOTE = (
    'Items with an "options" field are match-the-following questions: the question '
    "lists numbered items (Column A) and \"options\" is the lettered Column B. The "
    'answer pairs every number with a letter ("1-C"). Check each pair on its own; '
    "if any single pair is wrong, the verdict is \"incorrect\".\n\n"
)


def _match_note(questions: list[Question]) -> str:
    return _MATCH_NOTE if any(q.type == QuestionType.MATCH for q in questions) else ""


def _judge_item(i: int, q: Question) -> dict:
    item = {"index": i, "question": q.text, "marks": q.marks, "answer": q.answer}
    if q.type == QuestionType.MATCH:
        item["options"] = {_LETTERS_ALL[j]: opt for j, opt in enumerate(q.options or [])}
    return _with_figure(item, q)


def build_judge_prompt(questions: list[Question]) -> tuple[str, str]:
    items = [_judge_item(i, q) for i, q in enumerate(questions)]
    user = (
        f"{_context_line(questions)}\n\n{_figure_note(questions)}{_match_note(questions)}"
        "For each question below, judge whether the proposed answer is correct. "
        "Do not take it on trust: re-derive every calculation and check every "
        "factual claim yourself. Ignore style, wording and length. Verdicts: "
        '"correct" (right), "incorrect" (a factual or calculation error, or it '
        'does not answer the question), "uncertain" (you cannot tell).\n\n'
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        'Return ONLY a JSON object: {"results": [{"index": 0, "verdict": '
        '"correct" | "incorrect" | "uncertain", "reason": "one short sentence"}, ...]} '
        "with exactly one entry per question and no other text."
    )
    return VERIFIER_SYSTEM_PROMPT, user


def _key_index(q: Question) -> int | None:
    options = [o.strip() for o in (q.options or [])]
    try:
        return options.index(q.answer.strip())
    except ValueError:
        return None


def _mcq_verdict(q: Question, entry: dict) -> LlmVerdict:
    choice = str(entry.get("choice", "")).strip().upper()[:1]
    confidence = str(entry.get("confidence", "")).strip().lower()
    reasoning = _trim(entry.get("reasoning", ""), 200)
    key = _key_index(q)
    # (`"" in "ABCD"` is True in Python, hence the explicit length check)
    if len(choice) != 1 or choice not in _LETTERS or key is None or _LETTERS.index(choice) >= len(q.options or []):
        return LlmVerdict("uncertain", "The second AI check gave no usable answer.")
    if confidence == "low":
        return LlmVerdict("uncertain", "The second AI check was not confident which option is correct.")
    picked = _LETTERS.index(choice)
    if picked == key:
        return LlmVerdict(
            "agree", "Independently solved by a second AI pass: it chose the same option."
        )
    detail = (
        f'A second AI pass chose "{_trim(q.options[picked], 80)}" instead of the keyed '
        f'answer "{_trim(q.answer, 80)}"'
    )
    return LlmVerdict("disagree", _trim(f"{detail}. {reasoning}" if reasoning else f"{detail}."))


def _judge_verdict(q: Question, entry: dict) -> LlmVerdict:
    verdict = str(entry.get("verdict", "")).strip().lower()
    reason = _trim(entry.get("reason", ""), 200)
    if verdict == "correct":
        return LlmVerdict("agree", "Checked by a second AI pass: the answer appears correct.")
    if verdict == "incorrect":
        return LlmVerdict(
            "disagree",
            _trim(f"A second AI pass found a problem with the answer: {reason}" if reason
                  else "A second AI pass judged the answer incorrect."),
        )
    return LlmVerdict("uncertain", "The second AI check could not tell whether the answer is correct.")


async def llm_verdicts(
    client, questions: list[Question], chunk_size: int = 10
) -> list[LlmVerdict | None]:
    """One verdict per question, or None where the AI pass failed.

    All questions in a batch share a type; MCQs are solved blind, everything
    else is judged. A failed chunk never raises: its questions get None.
    """
    verdicts: list[LlmVerdict | None] = [None] * len(questions)
    size = max(1, chunk_size)
    for start in range(0, len(questions), size):
        chunk = questions[start : start + size]
        is_mcq = all(q.type == QuestionType.MCQ for q in chunk)
        system, user = build_mcq_prompt(chunk) if is_mcq else build_judge_prompt(chunk)
        try:
            raw = await client.complete_json(system, user)
        except GroqAPIError as e:
            logger.warning("Answer verification call failed, leaving chunk unverified: %s", e)
            continue
        if not isinstance(raw, list):
            continue
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < len(chunk):
                continue
            q = chunk[idx]
            try:
                verdicts[start + idx] = (
                    _mcq_verdict(q, entry) if q.type == QuestionType.MCQ else _judge_verdict(q, entry)
                )
            except Exception:  # a malformed entry must never sink the batch
                logger.warning("Unusable verification entry: %r", entry)
    return verdicts


# ---------------------------------------------------------------------------
# Putting the two together
# ---------------------------------------------------------------------------


def decide(rule: RuleResult, verdict: LlmVerdict | None, *, llm_attempted: bool) -> Verification:
    if rule.outcome == "ok":
        return Verification(VERIFIED, rule.detail)
    if rule.outcome == "mismatch":
        return Verification(REJECTED, rule.detail)
    if verdict is None:
        return Verification(
            UNVERIFIED,
            "The second AI check could not be completed."
            if llm_attempted
            else "No automatic check applied to this question.",
        )
    if verdict.outcome == "agree":
        return Verification(VERIFIED, verdict.detail)
    if verdict.outcome == "disagree":
        return Verification(REJECTED, verdict.detail)
    return Verification(UNVERIFIED, verdict.detail)


async def verify_questions(
    questions: list[Question],
    *,
    client,
    use_rules: bool = True,
    use_llm: bool = True,
    chunk_size: int = 10,
) -> list[Verification]:
    """Verify a batch. Never raises; returns one Verification per question."""
    if not questions:
        return []
    rules = [check_answer_rules(q) if use_rules else NOT_APPLICABLE for q in questions]

    verdicts: dict[int, LlmVerdict | None] = {}
    llm_attempted = bool(use_llm and client is not None)
    if llm_attempted:
        # Rule results are final: only spend the AI pass on what they left open.
        open_indices = [i for i, r in enumerate(rules) if r.outcome == "na"]
        if open_indices:
            got = await llm_verdicts(client, [questions[i] for i in open_indices], chunk_size)
            verdicts = dict(zip(open_indices, got))

    return [
        decide(rules[i], verdicts.get(i), llm_attempted=llm_attempted)
        for i in range(len(questions))
    ]
