from types import SimpleNamespace as NS

from app.services.export.answer_format import format_answer, split_label
from app.services.export.html import render_paper_html

ONE_LINE = (
    "1. Crop rotation - cereals plus millets. 2. Irrigation - canals; see Diagram "
    "Fig. 1. 3. Mechanisation - tractors. 4. Modern inputs - HYV seeds."
)


def test_inline_numbered_answer_splits_into_points():
    fa = format_answer(ONE_LINE, 5, "Long")
    assert len(fa.points) == 4
    assert fa.points[1].startswith("Irrigation")


def test_lead_in_and_trailing_reference_are_separated():
    fa = format_answer(
        "Political Changes: 1. Chola rule - centralised. 2. Vijayanagara - feudal. "
        "Reference: See the diagram 'Timeline'.",
        5, "Long",
    )
    assert fa.lead == "Political Changes"
    assert len(fa.points) == 2
    assert fa.reference.startswith("Reference:")


def test_marks_split_always_sums_to_marks():
    for marks in (2, 3, 5):
        for answer in (ONE_LINE, "F = ma. E = mc^2. p = mv. W = Fd.", "Plain prose answer here."):
            fa = format_answer(answer, marks, "Long" if marks == 5 else "Short")
            assert sum(m for _, m in fa.split) == marks


def test_one_mark_and_mcq_have_no_split():
    assert format_answer("Newton", 1, "Short").split == []
    assert format_answer("Option B", 1, "MCQ").split == []
    assert split_label([]) == ""


def test_diagram_and_equation_labels():
    fa = format_answer("1. Draw the diagram of a cell. 2. Force = mass x acceleration. 3. Explain.", 5, "Long")
    names = dict(fa.split)
    assert names["Diagram"] == 1 and names["Equation"] == 1 and names["Explanation"] == 3


def test_html_key_prints_points_and_split():
    q = NS(type=NS(value="Long"), text="Explain.", options=None, answer=ONE_LINE,
           explanation="meta note", grade=8)
    item = NS(question=q, order_index=0, effective_marks=5)
    paper = NS(title="T", subject=NS(name="Social Science"), items=[item], total_marks=5)
    html = render_paper_html(paper)
    assert html.count("<li>") == 4
    assert "Marks split: Diagram - 1, Explanation - 4" in html
    assert "meta note" not in html
