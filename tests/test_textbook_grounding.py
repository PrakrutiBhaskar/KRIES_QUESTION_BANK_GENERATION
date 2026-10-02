"""Textbook-grounded generation: ingest -> corpus -> coverage -> prompt -> grounding."""
import json

import pytest

from generation_engine.config import settings
from generation_engine.engine import GenerationEngine
from generation_engine.exceptions import InvalidRequestError
from generation_engine.prompts import build_prompt
from generation_engine.schemas import Difficulty, GenerationRequest, Question, QuestionType, Subject
from generation_engine.textbook import TextbookCorpus, select_passages
from generation_engine.textbook_ingest import build_corpus_dict, toc_entries
from generation_engine.validation import check_grounding

CH1 = (
    "Farmers grow crops in two main seasons. Kharif crops are sown in the rainy season from June "
    "to September. Rabi crops are sown in winter from October to March. Paddy and maize are Kharif "
    "crops while wheat and gram are Rabi crops. "
)
CH2 = (
    "Friction is the force that opposes the relative motion between two surfaces in contact. It acts "
    "opposite to the direction of motion. Rough surfaces produce more friction than smooth surfaces. "
    "Oil and grease reduce friction between the moving parts of machines. "
)


def pages():
    toc = "CONTENTS\n1. Crop Production ........ 2\n2. Friction ........ 4\n3. Sound ........ 6\n4. Light ........ 8"
    out = [toc]
    for title, body in [("Crop Production", CH1), ("Friction", CH2)]:
        out.append(f"Chapter\n{title}\n1.1 Basics\n{body * 3}")
        out.append(f"1.2 More\n{body * 3}")
    return out


@pytest.fixture
def corpus():
    result = build_corpus_dict(pages(), Subject.SCIENCE, 8, target_chars=300)
    c = TextbookCorpus()
    c.add_volume(result.corpus)
    return c


def test_toc_lines_parse_with_increasing_pages():
    entries = toc_entries("1. Crop Production ........ 2\n2. Friction ........ 4\n3. Sound  6")
    assert [t for t, _ in entries] == ["Crop Production", "Friction", "Sound"]


def test_ingest_finds_chapters_and_reports_missing_ones():
    result = build_corpus_dict(pages(), Subject.SCIENCE, 8, target_chars=300)
    titles = [c["title"] for c in result.corpus["chapters"]]
    assert titles == ["Crop Production", "Friction"]
    assert any("Sound" in w for w in result.warnings)  # in contents, never found -> reported, not invented
    assert all(p["id"].startswith("science-8-c") for c in result.corpus["chapters"] for p in c["passages"])


def test_scanned_pdf_is_refused():
    with pytest.raises(ValueError, match="scanned"):
        build_corpus_dict(["", "  "], Subject.SCIENCE, 8)


def test_syllabus_is_derived_from_textbooks_not_listed(corpus):
    d = corpus.to_syllabus_dict()
    assert d["Science"]["grades"]["8"] == ["Crop Production", "Friction"]
    assert "Math" not in d  # nothing ingested -> nothing in the syllabus


def test_coverage_visits_every_passage_before_repeating(corpus):
    ps = corpus.passages(Subject.SCIENCE, 8, "Crop Production")
    n = len(ps)
    assert n >= 3
    first = [p.id for p in select_passages(ps, n, 0)]
    assert sorted(first) == sorted(p.id for p in ps)
    # a later batch continues where the earlier one stopped
    a = [p.id for p in select_passages(ps, 2, 0)]
    b = [p.id for p in select_passages(ps, 2, 2)]
    assert set(a).isdisjoint(b)


def test_multi_part_volumes_merge_in_part_order():
    c = TextbookCorpus()
    v = lambda part, title: {"version": 1, "subject": "Math", "grade": 7, "part": part,
                             "chapters": [{"number": 1, "title": title,
                                           "passages": [{"id": f"m{part}", "section": "S", "text": "x " * 100}]}]}
    c.add_volume(v("2", "Second Book"))
    c.add_volume(v("1", "First Book"))
    assert [ch.title for ch in c.chapters(Subject.MATH, 7)] == ["First Book", "Second Book"]


def mk_req(**kw):
    base = dict(subject=Subject.SCIENCE, chapter="Crop Production", type=QuestionType.SHORT,
                grade=8, marks=2, difficulty=Difficulty.EASY, count=2)
    base.update(kw)
    return GenerationRequest(**base)


def test_prompt_contains_numbered_textbook_passages_and_passage_field(corpus):
    ps = select_passages(corpus.passages(Subject.SCIENCE, 8, "Crop Production"), 2)
    _, user = build_prompt(mk_req(), passages=ps)
    assert "[P1]" in user and "[P2]" in user
    assert "ONLY permitted source" in user
    assert '"passage"' in user


def q(text, answer):
    return Question(subject=Subject.SCIENCE, chapter="Crop Production", type=QuestionType.SHORT,
                    grade=8, text=text, answer=answer, marks=2, difficulty=Difficulty.EASY)


def test_grounding_passes_on_textbook_terms_and_fails_off_book():
    on = q("Name the crops sown in the rainy season from June to September.", "Kharif crops such as paddy and maize")
    off = q("Explain how neural networks learn using gradient descent algorithms.",
            "They adjust weights through backpropagation to minimise loss functions.")
    assert check_grounding(on, [CH1], 0.3) == []
    assert check_grounding(off, [CH1], 0.3)
    assert check_grounding(off, [CH1], 0) == []  # disabled


class Stub:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    async def complete_json(self, system_prompt, user_prompt):
        self.calls.append(user_prompt)
        return self.payload


@pytest.mark.asyncio
async def test_engine_writes_from_passages_tags_source_and_drops_ungrounded(corpus):
    good = {"text": "Which crops are sown in the rainy season from June to September?",
            "answer": "Kharif crops such as paddy and maize are sown then.", "passage": 1}
    off = {"text": "Explain how neural networks learn using gradient descent algorithms?",
           "answer": "They adjust weights through backpropagation to minimise loss functions.", "passage": 2}
    good2 = {"text": "Which crops are sown in winter between October and March?",
             "answer": "Rabi crops such as wheat and gram are sown in winter.", "passage": 2}
    engine = GenerationEngine(groq_client=Stub([good, off, good2]), textbooks=corpus)
    qs, report = await engine.generate(mk_req(count=2))
    assert len(qs) == 2
    assert all(any(t.startswith("src:science-8-c01") for t in x.tags) for x in qs)
    assert report.dropped_ungrounded == 1
    assert report.passages_total >= 3 and report.passages_used


@pytest.mark.asyncio
async def test_require_textbook_refuses_when_none_ingested():
    engine = GenerationEngine(groq_client=Stub([]), textbooks=TextbookCorpus(), require_textbook=True)
    with pytest.raises(InvalidRequestError, match="textbook"):
        await engine.generate(mk_req())


@pytest.mark.asyncio
async def test_unlisted_chapter_is_rejected_because_syllabus_comes_from_textbooks(corpus):
    engine = GenerationEngine(groq_client=Stub([]), textbooks=corpus)
    with pytest.raises(InvalidRequestError):
        await engine.generate(mk_req(chapter="Algebra"))
    with pytest.raises(InvalidRequestError):  # grade 8 book only
        await engine.generate(mk_req(grade=9))


def test_defaults_keep_existing_behaviour():
    assert settings.require_textbook is False
