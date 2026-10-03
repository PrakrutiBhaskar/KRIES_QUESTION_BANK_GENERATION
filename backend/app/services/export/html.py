"""
Paper -> HTML.

Used by the WeasyPrint renderer, and also useful on its own for a print
preview in the frontend. Layout follows a Karnataka State Board question
paper: header block (title, subject, grade, total marks), numbered questions
with per-question marks in the right margin, MCQ options as (a)-(d), then the
answer key on a fresh page.
"""
from __future__ import annotations

import base64
from html import escape

from ..figures import answer_key_figure, fit_size_mm, loaded_figure, read_figure_bytes
from .answer_format import format_answer, split_label


def item_section(item) -> str | None:
    """The item's section, or None. Tolerates items that predate sections."""
    return getattr(item, "section", None) or None


def section_totals(ordered_items) -> dict[str, int]:
    """Marks per section, for the heading line (blueprint papers only)."""
    totals: dict[str, int] = {}
    for item in ordered_items:
        section = item_section(item)
        if section:
            totals[section] = totals.get(section, 0) + item.effective_marks
    return totals

_STYLE = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-center { content: "Page " counter(page) " of " counter(pages);
                         font-size: 9pt; color: #666; } }
body { font-family: "Noto Sans", "Noto Sans Kannada", "DejaVu Sans", sans-serif;
       font-size: 11pt; line-height: 1.45; color: #111; }
.header { text-align: center; border-bottom: 2px solid #111; padding-bottom: 8px;
          margin-bottom: 14px; }
.header h1 { font-size: 15pt; margin: 0 0 4px; }
.meta { display: flex; justify-content: space-between; font-size: 10pt;
        color: #333; margin-top: 6px; }
.instructions { font-size: 9.5pt; color: #444; margin: 0 0 16px;
                border-left: 3px solid #ccc; padding-left: 8px; }
.section-head { display: flex; justify-content: space-between; font-weight: 700;
                font-size: 12pt; margin: 16px 0 8px; padding-bottom: 3px;
                border-bottom: 1px solid #111; page-break-after: avoid; }
.q { margin: 0 0 12px; page-break-inside: avoid; }
.q-head { display: flex; gap: 8px; align-items: baseline; }
.q-num { font-weight: 600; min-width: 22px; }
.q-text { flex: 1; }
.q-marks { font-weight: 600; white-space: nowrap; color: #333; }
.fig { margin: 6px 0 4px 30px; page-break-inside: avoid; }
.fig img { display: block; }
.fig .cap { font-size: 9pt; color: #555; font-style: italic; margin-top: 2px; }
.key .fig { margin-left: 30px; }
.options { margin: 4px 0 0 30px; padding: 0; list-style: none; }
.options li { margin: 2px 0; }
.section-break { page-break-before: always; }
.key h2 { font-size: 13pt; border-bottom: 1px solid #111; padding-bottom: 4px; }
.key .a { margin: 0 0 10px 30px; }
.key .a .label { font-weight: 600; }
.key .expl { color: #444; font-size: 10pt; }
.key .lead { font-weight: 600; margin: 2px 0; }
.key ol.pts { margin: 2px 0 4px 18px; padding-left: 14px; }
.key ol.pts li { margin: 2px 0; }
.key .ref { color: #444; font-size: 10pt; font-style: italic; margin: 2px 0; }
.key .split { display: inline-block; margin-top: 3px; padding: 2px 8px; font-size: 9.5pt;
              font-weight: 600; background: #eef0f6; border-radius: 4px; }
.footer-note { margin-top: 18px; font-size: 9pt; color: #777; text-align: center; }
"""

_OPTION_LABELS = "abcdefgh"


def figure_html(figure) -> str:
    """An inline <img> (data: URI, so the HTML is self-contained) for a figure.

    Returns "" when there is no figure or its file has gone missing, so a lost
    image never breaks the export. Sized in mm so WeasyPrint prints it at the
    same size the other two renderers use.
    """
    data = read_figure_bytes(figure)
    if data is None:
        return ""
    w, h = fit_size_mm(figure.width, figure.height)
    uri = f"data:{figure.mime};base64,{base64.b64encode(data).decode('ascii')}"
    alt = escape(figure.caption or "Figure", quote=True)
    cap = f"<div class='cap'>{escape(figure.caption)}</div>" if figure.caption else ""
    return (
        f"<div class='fig'><img src='{uri}' alt='{alt}' "
        f"style='width:{w}mm;height:{h}mm'>{cap}</div>"
    )


def _instructions(paper) -> str:
    """Standard rubric lines, tailored to what's actually in the paper."""
    types = {item.question.type.value for item in paper.items}
    lines = ["All questions are compulsory.", "Marks for each question are shown against it."]
    if "MCQ" in types:
        lines.append("For multiple-choice questions, write the letter of the correct option.")
    if "Long" in types:
        lines.append("Answer long-answer questions in full, showing all steps or points.")
    return "".join(f"<div>{escape(line)}</div>" for line in lines)


def render_paper_html(paper, *, include_answer_key: bool = True) -> str:
    """Build a complete standalone HTML document for a paper."""
    grades = sorted({item.question.grade for item in paper.items})
    grade_label = ", ".join(str(g) for g in grades) if grades else "-"

    parts: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{escape(paper.title)}</title>",
        f"<style>{_STYLE}</style></head><body>",
        "<div class='header'>",
        "<h1>Karnataka State Board</h1>",
        f"<div>{escape(paper.title)}</div>",
        "<div class='meta'>",
        f"<span>Subject: {escape(paper.subject.name)}</span>",
        f"<span>Grade: {escape(grade_label)}</span>",
        f"<span>Maximum Marks: {paper.total_marks}</span>",
        "</div></div>",
        f"<div class='instructions'>{_instructions(paper)}</div>",
    ]

    ordered = sorted(paper.items, key=lambda i: i.order_index)
    section_marks = section_totals(ordered)

    current_section = None
    for n, item in enumerate(ordered, start=1):
        q = item.question
        section = item_section(item)
        if section and section != current_section:
            current_section = section
            parts.append(
                f"<div class='section-head'><span>{escape(section)}</span>"
                f"<span>{section_marks[section]} marks</span></div>"
            )
        parts.append("<div class='q'><div class='q-head'>")
        parts.append(f"<span class='q-num'>{n}.</span>")
        parts.append(f"<span class='q-text'>{escape(q.text)}</span>")
        parts.append(f"<span class='q-marks'>[{item.effective_marks}]</span>")
        parts.append("</div>")
        parts.append(figure_html(loaded_figure(q, "figure")))
        if q.options:
            parts.append("<ul class='options'>")
            for label, option in zip(_OPTION_LABELS, q.options):
                parts.append(f"<li>({label}) {escape(str(option))}</li>")
            parts.append("</ul>")
        parts.append("</div>")

    if include_answer_key:
        parts.append("<div class='section-break key'><h2>Answer Key</h2>")
        for n, item in enumerate(ordered, start=1):
            q = item.question
            answer_fig = answer_key_figure(q)
            parts.append("<div class='a'>")
            if q.type.value == "MCQ":
                parts.append(
                    f"<div><span class='label'>{n}.</span> {escape(q.answer)}</div>"
                )
                if q.explanation:
                    parts.append(f"<div class='expl'>{escape(q.explanation)}</div>")
            else:
                fa = format_answer(
                    q.answer, item.effective_marks, q.type.value,
                    has_figure=answer_fig is not None,
                )
                parts.append(f"<div><span class='label'>{n}.</span>")
                if len(fa.points) > 1:
                    lead = fa.lead or f"[{item.effective_marks} marks]"
                    parts.append(f" <span class='lead'>{escape(lead)}</span>")
                if len(fa.points) > 1:
                    parts.append("</div><ol class='pts'>")
                    parts.extend(f"<li>{escape(p)}</li>" for p in fa.points)
                    parts.append("</ol>")
                else:
                    parts.append(f" {escape(fa.points[0] if fa.points else q.answer)}</div>")
                if fa.reference:
                    parts.append(f"<div class='ref'>{escape(fa.reference)}</div>")
                if fa.split:
                    parts.append(f"<div class='split'>{escape(split_label(fa.split))}</div>")
            # After the MCQ/descriptive branch so every question type can show one.
            parts.append(figure_html(answer_fig))
            parts.append("</div>")
        parts.append("</div>")

    parts.append(
        "<div class='footer-note'>Generated by the Question Bank Generator.</div>"
    )
    parts.append("</body></html>")
    return "".join(parts)
