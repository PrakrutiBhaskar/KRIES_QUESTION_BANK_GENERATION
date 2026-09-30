"""Kannada PDF export must work without WeasyPrint or system fonts."""
from types import SimpleNamespace as NS

import pytest

from app.config import settings
from app.services.export import renderer
from app.services.export.fpdf_renderer import fpdf_available

pytestmark = pytest.mark.skipif(not fpdf_available(), reason="fpdf2/uharfbuzz not installed")


def _paper():
    q = NS(
        type=NS(value="Short"), text="ಸಂಧಿ ಎಂದರೇನು?", options=None, grade=8,
        answer="1. ಎರಡು ಅಕ್ಷರಗಳು ಸೇರುವುದೇ ಸಂಧಿ. 2. ಉದಾಹರಣೆ: ಮನೆ + ಅಲ್ಲಿ. 3. ವ್ಯಾಕರಣ.",
        explanation="",
    )
    item = NS(question=q, order_index=0, effective_marks=3)
    return NS(title="ಕನ್ನಡ", subject=NS(name="Kannada"), items=[item], total_marks=3)


@pytest.mark.parametrize("choice", ["auto", "reportlab", "fpdf"])
def test_kannada_paper_renders_instead_of_erroring(monkeypatch, choice):
    monkeypatch.setattr(settings, "pdf_renderer", choice)
    monkeypatch.setattr(renderer, "weasyprint_available", lambda: False)
    pdf = renderer.render_pdf(_paper())
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000
