"""
Paper -> PDF via fpdf2 (pure pip, no system libraries).

This is the backend that makes Kannada work on machines where WeasyPrint's
native libraries (pango/cairo) aren't installed — notably Windows. fpdf2 runs
text through HarfBuzz (``uharfbuzz``), which does the glyph reordering and
conjunct (ottakshara) substitution Kannada needs. ReportLab cannot do that.

Fonts are bundled in ``backend/assets/fonts`` (Noto Sans + Noto Sans Kannada,
SIL Open Font License), so nothing has to be installed system-wide. Latin text
uses Noto Sans; any Kannada glyph falls back to Noto Sans Kannada per character,
so mixed English/Kannada lines render correctly.
"""
from __future__ import annotations

from pathlib import Path

from .answer_format import format_answer, split_label
from .html import item_section, section_totals

FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"

_OPTION_LABELS = "abcdefgh"
_LEFT = 16
_RIGHT = 16
_MARKS_W = 18


def fpdf_available() -> bool:
    """True if fpdf2, the shaping engine and the bundled fonts are all present."""
    try:
        import fpdf  # noqa: F401
        import uharfbuzz  # noqa: F401
    except Exception:
        return False
    return all(
        (FONT_DIR / name).exists()
        for name in ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf", "NotoSansKannada-Regular.ttf")
    )


def _instruction_lines(types: set[str]) -> list[str]:
    lines = ["All questions are compulsory.", "Marks for each question are shown against it."]
    if "MCQ" in types:
        lines.append("For multiple-choice questions, write the letter of the correct option.")
    if "Long" in types:
        lines.append("Answer long-answer questions in full, showing all steps or points.")
    return lines


def render_fpdf(paper) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    class _Paper(FPDF):
        def footer(self):  # runs on every page, inside the bottom margin
            self.set_y(-14)
            self.set_font("Noto", "", 9)
            self.set_text_color(102, 102, 102)
            self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="C")

    pdf = _Paper(format="A4", unit="mm")
    pdf.alias_nb_pages()
    pdf.set_margins(_LEFT, 18, _RIGHT)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_title(paper.title)
    pdf.set_author("Question Bank Generator")

    pdf.add_font("Noto", "", str(FONT_DIR / "NotoSans-Regular.ttf"))
    pdf.add_font("Noto", "B", str(FONT_DIR / "NotoSans-Bold.ttf"))
    italic = FONT_DIR / "NotoSans-Italic.ttf"
    pdf.add_font("Noto", "I", str(italic if italic.exists() else FONT_DIR / "NotoSans-Regular.ttf"))
    pdf.add_font("NotoKn", "", str(FONT_DIR / "NotoSansKannada-Regular.ttf"))
    kn_bold = FONT_DIR / "NotoSansKannada-Bold.ttf"
    pdf.add_font("NotoKn", "B", str(kn_bold if kn_bold.exists() else FONT_DIR / "NotoSansKannada-Regular.ttf"))
    pdf.set_fallback_fonts(["NotoKn"], exact_match=False)
    pdf.set_text_shaping(True)

    pdf.add_page()
    epw = pdf.epw

    def write(text, w=0, h=5.6, style="", size=11, align="L", color=(17, 17, 17)):
        pdf.set_font("Noto", style, size)
        pdf.set_text_color(*color)
        pdf.multi_cell(w, h, text, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    ordered = sorted(paper.items, key=lambda i: i.order_index)
    grades = sorted({item.question.grade for item in ordered})
    grade_label = ", ".join(str(g) for g in grades) if grades else "-"

    # --- header -------------------------------------------------------
    write("Karnataka State Board", style="B", size=15, align="C", h=7)
    write(paper.title, size=11, align="C")
    pdf.ln(1)
    pdf.set_font("Noto", "", 9.5)
    third = epw / 3
    pdf.cell(third, 6, f"Subject: {paper.subject.name}")
    pdf.cell(third, 6, f"Grade: {grade_label}", align="C")
    pdf.cell(third, 6, f"Maximum Marks: {paper.total_marks}", align="R",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(17, 17, 17)
    pdf.set_line_width(0.4)
    pdf.line(_LEFT, pdf.get_y(), _LEFT + epw, pdf.get_y())
    pdf.ln(3)

    types = {item.question.type.value for item in ordered}
    for line in _instruction_lines(types):
        pdf.set_x(_LEFT + 2)
        write(line, size=9.5, h=4.8, color=(68, 68, 68), w=epw - 2)
    pdf.ln(4)

    # --- questions ----------------------------------------------------
    section_marks = section_totals(ordered)
    current_section = None
    for n, item in enumerate(ordered, start=1):
        q = item.question
        if pdf.will_page_break(28):
            pdf.add_page()
        section = item_section(item)
        if section and section != current_section:
            current_section = section
            pdf.ln(2)
            y = pdf.get_y()
            pdf.set_font("Noto", "B", 12)
            pdf.set_xy(_LEFT + epw - 40, y)
            pdf.cell(40, 6, f"{section_marks[section]} marks", align="R")
            pdf.set_xy(_LEFT, y)
            write(section, w=epw - 40, style="B", size=12, h=6)
            pdf.set_line_width(0.2)
            pdf.line(_LEFT, pdf.get_y(), _LEFT + epw, pdf.get_y())
            pdf.ln(3)
        y0 = pdf.get_y()
        pdf.set_font("Noto", "B", 11)
        pdf.set_xy(_LEFT + epw - _MARKS_W, y0)
        pdf.cell(_MARKS_W, 5.6, f"[{item.effective_marks}]", align="R")
        pdf.set_xy(_LEFT, y0)
        write(f"{n}. {q.text}", w=epw - _MARKS_W)
        if q.options:
            for label, option in zip(_OPTION_LABELS, q.options):
                pdf.set_x(_LEFT + 8)
                write(f"({label}) {option}", w=epw - 8, size=10.5, h=5.2)
        pdf.ln(3)

    # --- answer key ---------------------------------------------------
    pdf.add_page()
    write("Answer Key", style="B", size=13, h=7)
    pdf.set_line_width(0.2)
    pdf.line(_LEFT, pdf.get_y(), _LEFT + epw, pdf.get_y())
    pdf.ln(3)

    for n, item in enumerate(ordered, start=1):
        q = item.question
        if pdf.will_page_break(24):
            pdf.add_page()
        if q.type.value == "MCQ":
            write(f"{n}. {q.answer}", w=epw)
            if q.explanation:
                pdf.set_x(_LEFT + 6)
                write(q.explanation, w=epw - 6, size=9.5, h=4.8, color=(68, 68, 68))
        else:
            fa = format_answer(q.answer, item.effective_marks, q.type.value)
            if len(fa.points) > 1:
                head = f"{n}. {fa.lead}" if fa.lead else f"{n}. [{item.effective_marks} marks]"
                write(head, w=epw, style="B" if fa.lead else "")
                for i, point in enumerate(fa.points, start=1):
                    pdf.set_x(_LEFT + 6)
                    pdf.set_font("Noto", "", 10.5)
                    pdf.cell(7, 5.4, f"{i}.")
                    write(point, w=epw - 13, size=10.5, h=5.4)
            else:
                write(f"{n}. {fa.points[0] if fa.points else q.answer}", w=epw)
            if fa.reference:
                pdf.set_x(_LEFT + 6)
                write(fa.reference, w=epw - 6, style="I", size=9.5, h=4.8, color=(68, 68, 68))
            if fa.split:
                pdf.set_x(_LEFT + 6)
                write(split_label(fa.split), w=epw - 6, style="B", size=9.5, h=5, color=(43, 58, 103))
        pdf.ln(2.5)

    return bytes(pdf.output())
