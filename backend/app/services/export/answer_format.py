"""
Answer-key formatting shared by both PDF renderers.

Turns the model's free-text ``answer`` into:

  * a list of discrete points (so the PDF prints one point per line instead of
    a run-on paragraph), and
  * a marks split ("Diagram - 1, Explanation - 3, ...") that adds up to the
    question's marks.

Answers arrive in a few shapes — "1. ... 2. ..." on one line, one point per
line, "Causes: ... Effects: ..." labelled sections, or plain prose — and may
carry a lead-in ("Political Changes: 1. ...") or a trailing "Reference: see
the diagram ..." line. ``format_answer`` handles all of them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from generation_engine.schemas import parse_match_answer

# Numbered ("1." / "1)") or bulleted markers. Trailing whitespace is required so
# decimals such as "2.5 kg" are not mistaken for markers.
_MARKER = re.compile(r"(?:\d+[.)]|[-*\u2022])\s+")
_SENTENCE_END = ".!?\u0964"  # includes the Kannada/Devanagari danda
_LABEL = re.compile(r"(?:^|(?<=\s))([A-Z][A-Za-z ]{2,24}):\s+")
_TRAILING_REF = re.compile(
    r"(?:^|\s)((?:Reference|Diagram|Note|Fig(?:ure)?)\s*:\s.*)$", re.IGNORECASE | re.DOTALL
)

_DIAGRAM_WORDS = re.compile(r"\b(diagram|figure|fig\.?|sketch|draw|labelled|labeled|flowchart|map)\b", re.I)
# A formula/equation: an "=" between two operands, or a chemical/physical arrow.
_EQUATION = re.compile(r"[A-Za-z0-9)\]]\s*=\s*[A-Za-z0-9(\[-]|\u2192|->")


@dataclass
class FormattedAnswer:
    lead: str = ""                                   # heading before point 1, if any
    points: list[str] = field(default_factory=list)  # the numbered points
    reference: str = ""                              # trailing "Reference: ..." line
    split: list[tuple[str, int]] = field(default_factory=list)  # (component, marks)


def _is_boundary(text: str, pos: int) -> bool:
    i = pos
    while i > 0 and text[i - 1] in " \t":
        i -= 1
    return i == 0 or text[i - 1] == "\n" or text[i - 1] in _SENTENCE_END or text[i - 1] == ":"


def _split_markers(text: str) -> tuple[str, list[str]]:
    matches = [m for m in _MARKER.finditer(text) if _is_boundary(text, m.start())]
    if len(matches) < 2:
        return "", []
    lead = text[: matches[0].start()].strip()
    points = []
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[m.end():end].strip()
        if chunk:
            points.append(chunk)
    return lead, points


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?\u0964])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def split_points(answer: str) -> tuple[str, list[str], str]:
    """Return (lead, points, reference) for an answer string."""
    text = (answer or "").strip()
    if not text:
        return "", [], ""

    reference = ""
    ref = _TRAILING_REF.search(text)
    # Only peel a trailing reference off when something precedes it.
    if ref and ref.start(1) > 0:
        reference = ref.group(1).strip()
        text = text[: ref.start(1)].strip()

    lead, points = _split_markers(text)
    if points:
        return lead.rstrip(":").strip(), points, reference

    labels = list(_LABEL.finditer(text))
    if len(labels) >= 2:
        points = []
        for idx, m in enumerate(labels):
            end = labels[idx + 1].start() if idx + 1 < len(labels) else len(text)
            body = text[m.end():end].strip()
            if body:
                points.append(f"{m.group(1)}: {body}")
        if points:
            return "", points, reference

    lines = [ln.strip(" -*\u2022\t") for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return "", lines, reference

    return "", _split_sentences(text), reference


def _classify(point: str) -> str:
    if _DIAGRAM_WORDS.search(point):
        return "Diagram"
    if _EQUATION.search(point):
        return "Equation"
    return "Explanation"


def marks_split(
    points: list[str],
    reference: str,
    marks: int,
    qtype: str,
    has_figure: bool = False,
) -> list[tuple[str, int]]:
    """
    Distribute ``marks`` over Diagram / Equation / Explanation.

    Rules (deterministic, so the split always sums to the question's marks):
      * 1-mark and MCQ questions carry no split.
      * A diagram mention (in a point or the trailing reference) earns 1 mark,
        and so does an answer-key figure attached to the question (``has_figure``):
        the diagram printed there is the diagram being marked.
      * Each equation/formula point earns 1 mark, keeping at least 1 mark for
        explanation.
      * Everything left is Explanation.
    """
    if marks <= 1 or qtype == "MCQ":
        return []

    kinds = [_classify(p) for p in points]
    has_diagram = (
        has_figure
        or "Diagram" in kinds
        or bool(reference and _DIAGRAM_WORDS.search(reference))
    )
    n_equations = kinds.count("Equation")

    diagram = 1 if has_diagram else 0
    # Leave at least one mark for explanation.
    equation = min(n_equations, max(marks - diagram - 1, 0))
    explanation = marks - diagram - equation

    out: list[tuple[str, int]] = []
    if diagram:
        out.append(("Diagram", diagram))
    if equation:
        out.append(("Equation", equation))
    if explanation:
        out.append(("Explanation", explanation))
    return out


def format_answer(
    answer: str, marks: int, qtype: str, has_figure: bool = False
) -> FormattedAnswer:
    lead, points, reference = split_points(answer)
    return FormattedAnswer(
        lead=lead,
        points=points,
        reference=reference,
        split=marks_split(points, reference, marks, qtype, has_figure),
    )


def split_label(split: list[tuple[str, int]]) -> str:
    """'Marks split: Diagram - 1, Explanation - 4' (empty string when no split)."""
    if not split:
        return ""
    return "Marks split: " + ", ".join(f"{name} - {m}" for name, m in split)


def match_key_label(answer: str) -> str:
    """A Match answer key as printed: "1 - b, 2 - a, 3 - c".

    The paper prints Column B as (a), (b), (c), so the key uses the same
    lowercase letters. An answer that is not in pair form is returned as it is
    rather than hidden.
    """
    mapping = parse_match_answer(answer)
    if not mapping:
        return answer
    return ",   ".join(f"{n} - {mapping[n].lower()}" for n in sorted(mapping))
