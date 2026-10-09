"""
Paper -> PDF bytes.

Two backends, selected by the `PDF_RENDERER` setting:

  * **weasyprint** (preferred) — renders the HTML in html.py. It shapes
    complex scripts correctly via Pango/HarfBuzz, which matters because
    Kannada is one of the five subjects: Kannada text needs glyph
    reordering and ligature substitution that simpler PDF writers don't do.
    Needs system libraries (pango, cairo, gdk-pixbuf), so it isn't always
    installed.

  * **reportlab** — pure-pip fallback, no system dependencies, so it works on
    a bare Render/AWS container. Fine for Latin-script subjects. For Kannada
    it needs a Unicode TTF registered (see `_register_fonts`); without one,
    ReportLab's built-in fonts have no Kannada glyphs and the text would come
    out as blank boxes, so we refuse rather than emit a broken PDF.

`auto` prefers WeasyPrint and falls back to ReportLab.
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from ...config import settings
from ...errors import ServiceUnavailableError
from ..figures import answer_key_figure, fit_size_mm, loaded_figure, read_figure_bytes
from .answer_format import MATCH_COLUMN_HEADINGS, format_answer, match_key_label, match_layout, split_label
from .fpdf_renderer import fpdf_available, render_fpdf
from .html import item_section, ordered_items, render_paper_html, section_totals

logger = logging.getLogger("backend.export")

_OPTION_LABELS = "abcdefgh"

# Candidate Unicode fonts for the ReportLab backend, most preferred first.
_FONT_CANDIDATES = {
    "body": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "kannada": [
        "/usr/share/fonts/truetype/noto/NotoSansKannada-Regular.ttf",
        "/usr/share/fonts/truetype/fonts-kalapi/Kedage-n.ttf",
    ],
}

_fonts_registered: dict[str, str] | None = None


def weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # ImportError, or OSError for missing system libs
        return False
    return True


def _register_fonts() -> dict[str, str]:
    """Register the first available Unicode TTFs; returns the font-name map."""
    global _fonts_registered
    if _fonts_registered is not None:
        return _fonts_registered

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    mapping = {"body": "Helvetica", "bold": "Helvetica-Bold", "kannada": ""}
    for role, paths in _FONT_CANDIDATES.items():
        for path in paths:
            if not Path(path).exists():
                continue
            name = f"QB-{role}"
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception as exc:  # pragma: no cover - font-specific
                logger.debug("Could not register %s: %s", path, exc)
                continue
            mapping[role] = name
            break

    _fonts_registered = mapping
    return mapping


def _render_weasyprint(paper, include_answer_key: bool = True) -> bytes:
    from weasyprint import HTML

    html = render_paper_html(paper, include_answer_key=include_answer_key)
    return HTML(string=html).write_pdf()


def _render_reportlab(paper, include_answer_key: bool = True) -> bytes:
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image as RLImage,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    fonts = _register_fonts()
    body_font, bold_font = fonts["body"], fonts["bold"]

    if _needs_kannada(paper) and not fonts["kannada"]:
        raise ServiceUnavailableError(
            "Kannada papers need either WeasyPrint (recommended) or a Kannada "
            "Unicode font installed for the ReportLab backend. Install "
            "fonts-noto-core, or set PDF_RENDERER=weasyprint."
        )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "qb-title", parent=base["Title"], fontName=bold_font, fontSize=15,
            alignment=TA_CENTER, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "qb-subtitle", parent=base["Normal"], fontName=body_font, fontSize=11,
            alignment=TA_CENTER, spaceAfter=8,
        ),
        "meta": ParagraphStyle(
            "qb-meta", parent=base["Normal"], fontName=body_font, fontSize=9.5,
        ),
        "instr": ParagraphStyle(
            "qb-instr", parent=base["Normal"], fontName=body_font, fontSize=9.5,
            textColor="#444444", leftIndent=6, spaceAfter=2,
        ),
        "q": ParagraphStyle(
            "qb-q", parent=base["Normal"], fontName=body_font, fontSize=11, leading=15,
        ),
        "marks": ParagraphStyle(
            "qb-marks", parent=base["Normal"], fontName=bold_font, fontSize=11,
            alignment=2,
        ),
        "opt": ParagraphStyle(
            "qb-opt", parent=base["Normal"], fontName=body_font, fontSize=10.5,
            leftIndent=22, leading=14,
        ),
        "section": ParagraphStyle(
            "qb-section", parent=base["Normal"], fontName=bold_font, fontSize=12,
            spaceBefore=6, spaceAfter=6, keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "qb-h2", parent=base["Heading2"], fontName=bold_font, fontSize=13,
            spaceAfter=6,
        ),
        "pt": ParagraphStyle(
            "qb-pt", parent=base["Normal"], fontName=body_font, fontSize=10.5, leading=14,
            leftIndent=36, firstLineIndent=-14, spaceAfter=1.5,
        ),
        "lead": ParagraphStyle(
            "qb-lead", parent=base["Normal"], fontName=bold_font, fontSize=10.5, leading=14,
            leftIndent=22,
        ),
        "split": ParagraphStyle(
            "qb-split", parent=base["Normal"], fontName=bold_font, fontSize=9.5,
            leftIndent=22, spaceBefore=2, textColor="#2b3a67",
        ),
        "expl": ParagraphStyle(
            "qb-expl", parent=base["Normal"], fontName=body_font, fontSize=9.5,
            textColor="#444444", leftIndent=22,
        ),
        "cap": ParagraphStyle(
            "qb-cap", parent=base["Normal"], fontName=body_font, fontSize=9,
            textColor="#555555", leading=11, spaceBefore=2,
        ),
    }

    def figure_flowables(figure, indent_mm: float) -> list:
        """The figure (and its caption) as one indented block; [] if unavailable."""
        data = read_figure_bytes(figure)
        if data is None:
            return []
        w_mm, h_mm = fit_size_mm(figure.width, figure.height)
        img = RLImage(BytesIO(data), width=w_mm * mm, height=h_mm * mm)
        img.hAlign = "LEFT"
        cells = [[img]]
        if figure.caption:
            cells.append([Paragraph(_esc(figure.caption), styles["cap"])])
        col = max(w_mm, 90.0) * mm
        block = Table(cells, colWidths=[col + indent_mm * mm], hAlign="LEFT")
        block.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), indent_mm * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return [Spacer(1, 3), block]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title=paper.title,
        author="Question Bank Generator",
    )

    ordered = ordered_items(paper)
    grades = sorted({item.question.grade for item in ordered})
    grade_label = ", ".join(str(g) for g in grades) if grades else "-"

    flow = [
        Paragraph("Karnataka State Board", styles["title"]),
        Paragraph(_esc(paper.title), styles["subtitle"]),
    ]

    meta = Table(
        [[
            Paragraph(f"Subject: {_esc(paper.subject.name)}", styles["meta"]),
            Paragraph(f"Grade: {grade_label}", styles["meta"]),
            Paragraph(f"Maximum Marks: {paper.total_marks}", styles["meta"]),
        ]],
        colWidths=[doc.width / 3.0] * 3,
    )
    meta.setStyle(
        TableStyle([
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, "#111111"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ])
    )
    flow += [meta, Spacer(1, 8)]

    for line in _instruction_lines(ordered):
        flow.append(Paragraph(_esc(line), styles["instr"]))
    flow.append(Spacer(1, 10))

    section_marks = section_totals(ordered)
    current_section = None
    for n, item in enumerate(ordered, start=1):
        q = item.question
        section = item_section(item)
        if section and section != current_section:
            current_section = section
            flow.append(Paragraph(
                f"{_esc(section)} &nbsp;&nbsp;({section_marks[section]} marks)",
                styles["section"],
            ))
        match = match_layout(q.text, q.options) if q.type.value == "Match" else None
        row = Table(
            [[
                Paragraph(f"{n}. {_esc(match[0] if match else q.text)}".replace("\n", "<br/>"), styles["q"]),
                Paragraph(f"[{item.effective_marks}]", styles["marks"]),
            ]],
            colWidths=[doc.width - 18 * mm, 18 * mm],
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        block = [row]
        fig_block = figure_flowables(loaded_figure(q, "figure"), 8)
        block.extend(fig_block)
        if match:
            head = ParagraphStyle("qb-match-head", parent=styles["opt"], fontName=bold_font)
            data = [[Paragraph(_esc(h), head) for h in MATCH_COLUMN_HEADINGS]]
            data += [[Paragraph(_esc(a), styles["opt"]), Paragraph(_esc(b), styles["opt"])] for a, b in match[1]]
            col = (doc.width - 26 * mm) / 2
            grid = Table(data, colWidths=[col, col], hAlign="RIGHT", repeatRows=1)
            grid.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.6, "#444444"),
                ("BACKGROUND", (0, 0), (-1, 0), "#f0f0f0"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            block.append(Spacer(1, 3))
            block.append(grid)
        elif q.options:
            for label, option in zip(_OPTION_LABELS, q.options):
                block.append(Paragraph(f"({label}) {_esc(str(option))}", styles["opt"]))
        # A figure must stay on the same page as the question it belongs to.
        # Questions without one flow exactly as before.
        if fig_block:
            flow.append(KeepTogether(block))
        else:
            flow.extend(block)
        flow.append(Spacer(1, 7))

    if include_answer_key:
        flow.append(PageBreak())
        flow.append(Paragraph("Answer Key", styles["h2"]))
        for n, item in enumerate(ordered, start=1):
            q = item.question
            answer_fig = answer_key_figure(q)
            block = []
            if q.type.value == "MCQ":
                block.append(Paragraph(f"{n}. {_esc(q.answer)}", styles["q"]))
                if q.explanation:
                    block.append(Paragraph(_esc(q.explanation), styles["expl"]))
            elif q.type.value == "Match":
                block.append(Paragraph(f"{n}. {_esc(match_key_label(q.answer))}", styles["q"]))
            else:
                fa = format_answer(
                    q.answer, item.effective_marks, q.type.value,
                    has_figure=answer_fig is not None,
                )
                if len(fa.points) > 1:
                    head = f"{n}. {_esc(fa.lead)}" if fa.lead else f"{n}. [{item.effective_marks} marks]"
                    block.append(Paragraph(head, styles["q"]))
                    for i, point in enumerate(fa.points, start=1):
                        block.append(Paragraph(f"{i}.&nbsp;&nbsp;{_esc(point)}", styles["pt"]))
                else:
                    text = fa.points[0] if fa.points else q.answer
                    block.append(Paragraph(f"{n}. {_esc(text)}", styles["q"]))
                if fa.reference:
                    block.append(Paragraph(f"<i>{_esc(fa.reference)}</i>", styles["expl"]))
                if fa.split:
                    block.append(Paragraph(_esc(split_label(fa.split)), styles["split"]))
            fig_block = figure_flowables(answer_fig, 22)
            block.extend(fig_block)
            if fig_block:
                flow.append(KeepTogether(block))
            else:
                flow.extend(block)
            flow.append(Spacer(1, 6))

    doc.build(flow)
    return buf.getvalue()


def render_pdf(paper, *, include_answer_key: bool = True) -> bytes:
    """Render a paper to PDF bytes using the configured backend.

    With `include_answer_key=False` the PDF holds the question paper only.
    """
    choice = settings.pdf_renderer
    if choice == "weasyprint":
        if not weasyprint_available():
            raise ServiceUnavailableError(
                "PDF_RENDERER=weasyprint but WeasyPrint is not importable. "
                "Install it and its system libraries, or set PDF_RENDERER=auto."
            )
        return _render_weasyprint(paper, include_answer_key)
    if choice == "fpdf":
        if not fpdf_available():
            raise ServiceUnavailableError(_FPDF_HELP)
        return render_fpdf(paper, include_answer_key=include_answer_key)
    if choice == "reportlab":
        return _render_reportlab_or_fpdf(paper, include_answer_key)

    if weasyprint_available():
        try:
            return _render_weasyprint(paper, include_answer_key)
        except Exception as exc:  # pragma: no cover - runtime-specific
            logger.warning("WeasyPrint failed, falling back: %s", exc)
    return _render_reportlab_or_fpdf(paper, include_answer_key)


_FPDF_HELP = (
    "Kannada PDF export needs either WeasyPrint or the pure-pip fpdf2 renderer. "
    "Run: pip install fpdf2 uharfbuzz  (the fonts are bundled in backend/assets/fonts), "
    "then restart the backend."
)


def _render_reportlab_or_fpdf(paper, include_answer_key: bool = True) -> bytes:
    """ReportLab can't shape Kannada, so Kannada papers go to fpdf2 instead."""
    if _needs_kannada(paper):
        if not fpdf_available():
            raise ServiceUnavailableError(_FPDF_HELP)
        return render_fpdf(paper, include_answer_key=include_answer_key)
    return _render_reportlab(paper, include_answer_key)


def active_renderer() -> str:
    """Which backend `render_pdf` would use right now — surfaced by /health."""
    if settings.pdf_renderer != "auto":
        return settings.pdf_renderer
    return "weasyprint" if weasyprint_available() else "reportlab"


def _needs_kannada(paper) -> bool:
    if paper.subject.name == "Kannada":
        return True
    return any(_has_kannada(item.question.text) for item in paper.items)


def _has_kannada(text: str) -> bool:
    # Kannada block: U+0C80-U+0CFF
    return any("\u0c80" <= ch <= "\u0cff" for ch in text)


def _instruction_lines(items) -> list[str]:
    types = {item.question.type.value for item in items}
    lines = [
        "All questions are compulsory.",
        "Marks for each question are shown against it.",
    ]
    if "MCQ" in types:
        lines.append(
            "For multiple-choice questions, write the letter of the correct option."
        )
    if "Long" in types:
        lines.append(
            "Answer long-answer questions in full, showing all steps or points."
        )
    if "Fill" in types:
        lines.append("For fill-in-the-blank questions, write the missing word or phrase.")
    if "Match" in types:
        lines.append(
            "For match-the-following questions, write the letter of the matching "
            "option against each number."
        )
    return lines


# Groq's output routinely contains typographic punctuation and scientific
# notation (non-breaking hyphens, subscript/superscript digits for CO2, O2,
# exponents, etc.) that base-14 PDF fonts — and some system TTFs, depending
# on what's installed on the host — simply have no glyph for. ReportLab
# drops or box-renders anything the active font can't map, silently, so a
# missing glyph never surfaces as an error. Normalizing to plain ASCII
# before layout guarantees correct rendering regardless of which font ends
# up registered on a given machine.
_CHAR_NORMALIZE_MAP = {
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2015": "-",  # horizontal bar
    "\u2212": "-",  # minus sign
    "\u2018": "'", "\u2019": "'",  # curly single quotes
    "\u201c": '"', "\u201d": '"',  # curly double quotes
    "\u2026": "...",  # ellipsis
    "\u00a0": " ",  # non-breaking space
    "\u00d7": "x",  # multiplication sign
    "\u00f7": "/",  # division sign
    # Subscript digits (e.g. CO2, O2)
    "\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4",
    "\u2085": "5", "\u2086": "6", "\u2087": "7", "\u2088": "8", "\u2089": "9",
    # Superscript digits (e.g. exponents)
    "\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3", "\u2074": "4",
    "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9",
}
_CHAR_NORMALIZE_TABLE = str.maketrans(_CHAR_NORMALIZE_MAP)


def _normalize_text(text: str) -> str:
    """Map characters base-14/system fonts commonly can't render to ASCII."""
    return str(text).translate(_CHAR_NORMALIZE_TABLE)


def _esc(text: str) -> str:
    """Normalize, then escape for ReportLab's mini-HTML paragraph markup."""
    return (
        _normalize_text(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
