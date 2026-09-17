"""
Engine-level tests — the rows of test-plan.md Section 1 that the unit tests
for schemas/prompts/validation don't reach: batch of N, duplicate-free
output, and the 400 / 502 / 422 error paths.

The Groq call is stubbed throughout; nothing here hits the network.
"""
import pytest

from generation_engine.config import reload_settings
from generation_engine.engine import GenerationEngine
from generation_engine.exceptions import (
    GenerationValidationError,
    GroqAPIError,
    InvalidRequestError,
)
from generation_engine.schemas import (
    Difficulty,
    GenerationRequest,
    QuestionType,
    Subject,
)
from generation_engine.syllabus import SyllabusIndex


# --- stubs ---------------------------------------------------------------


class StubGroq:
    """Returns a scripted payload per call; records the prompts it received."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    async def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if not self.payloads:
            return []
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        if isinstance(payload, Exception):
            raise payload
        return payload


_MCQ_BANK = [
    ("Which gas do plants absorb during photosynthesis?",
     ["Carbon dioxide", "Oxygen", "Nitrogen", "Hydrogen"], "Carbon dioxide",
     "Plants take in carbon dioxide to make glucose."),
    ("Where in the plant cell does photosynthesis occur?",
     ["Chloroplast", "Nucleus", "Vacuole", "Ribosome"], "Chloroplast",
     "Chloroplasts contain the chlorophyll that captures light."),
    ("What is the green pigment in leaves called?",
     ["Chlorophyll", "Haemoglobin", "Carotene", "Melanin"], "Chlorophyll",
     "Chlorophyll gives leaves their green colour."),
    ("Which by-product is released during photosynthesis?",
     ["Oxygen", "Methane", "Ammonia", "Sulphur dioxide"], "Oxygen",
     "Oxygen is released when water molecules are split."),
    ("What food is stored in leaves after photosynthesis?",
     ["Starch", "Protein", "Fat", "Cellulose"], "Starch",
     "Glucose is converted to starch for storage."),
    ("Which part of the leaf allows gas exchange?",
     ["Stomata", "Midrib", "Petiole", "Cuticle"], "Stomata",
     "Stomata are the pores through which gases enter and leave."),
]


def mcq_item(n):
    """Returns a genuinely distinct MCQ — near-identical texts are correctly
    dropped by the duplicate checker, so fixtures must differ in substance."""
    text, options, answer, explanation = _MCQ_BANK[n % len(_MCQ_BANK)]
    return {
        "text": text,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "topic": "Photosynthesis",
        "tags": ["biology"],
    }


_THREE_MARK_BANK = [
    ("Explain the process of photosynthesis.",
     "1. Chlorophyll in the leaves absorbs sunlight. "
     "2. Carbon dioxide and water are converted into glucose. "
     "3. Oxygen is released as a by-product."),
    ("Describe how water reaches the leaves of a tall tree.",
     "1. Roots absorb water from the soil by osmosis. "
     "2. Xylem vessels carry the water upward as a continuous column. "
     "3. Transpiration from the leaves pulls the column up."),
    ("State three conditions required for photosynthesis.",
     "1. Sunlight is needed as the energy source. "
     "2. Carbon dioxide must be available through the stomata. "
     "3. Water must be supplied by the roots."),
]


def three_mark_item(n):
    text, answer = _THREE_MARK_BANK[n % len(_THREE_MARK_BANK)]
    return {
        "text": text,
        "answer": answer,
        "explanation": "Covers inputs, process and outputs.",
        "topic": "Photosynthesis",
        "tags": ["biology"],
    }


def make_request(**overrides):
    base = dict(
        subject=Subject.SCIENCE,
        chapter="Nutrition in Plants",
        type=QuestionType.MCQ,
        grade=8,
        marks=1,
        difficulty=Difficulty.EASY,
        count=3,
    )
    base.update(overrides)
    return GenerationRequest(**base)


@pytest.fixture(autouse=True)
def fresh_settings():
    reload_settings()
    yield
    reload_settings()


# --- happy paths ---------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_exactly_n_questions():
    payload = [mcq_item(i) for i in range(3)]
    engine = GenerationEngine(groq_client=StubGroq(payload))
    questions, report = await engine.generate(make_request(count=3))

    assert len(questions) == 3
    assert report.returned_count == 3
    assert report.attempts == 1


@pytest.mark.asyncio
async def test_three_mark_inline_numbering_is_accepted():
    """
    Regression: the 3-mark prompt asks the model to number points inline, and
    models routinely return all three on one line. A line-anchored splitter
    counted six sentences instead of three and rejected valid output.
    """
    payload = [three_mark_item(i) for i in range(2)]
    request = make_request(type=QuestionType.SHORT, marks=3, count=2)
    engine = GenerationEngine(groq_client=StubGroq(payload))

    questions, report = await engine.generate(request)
    assert len(questions) == 2
    assert report.dropped_marks_format_invalid == 0


@pytest.mark.asyncio
async def test_one_mark_descriptive_questions_generate():
    payload = [
        {"text": "What is the SI unit of force?", "answer": "Newton", "explanation": ""},
        {"text": "Name the gas released during photosynthesis.", "answer": "Oxygen",
         "explanation": ""},
    ]
    request = make_request(type=QuestionType.SHORT, marks=1, count=2)
    engine = GenerationEngine(groq_client=StubGroq(payload))

    questions, _ = await engine.generate(request)
    assert [q.marks for q in questions] == [1, 1]
    assert all(q.options is None for q in questions)


@pytest.mark.asyncio
async def test_generated_fields_are_filled_from_request():
    engine = GenerationEngine(groq_client=StubGroq([mcq_item(0)]))
    questions, _ = await engine.generate(make_request(count=1))
    q = questions[0]

    assert q.subject == Subject.SCIENCE
    assert q.chapter == "Nutrition in Plants"
    assert q.type == QuestionType.MCQ
    assert q.difficulty == Difficulty.EASY
    assert q.id


# --- duplicates ----------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicates_within_a_batch_are_dropped():
    duplicated = [mcq_item(0), mcq_item(0), mcq_item(1)]
    unique = [mcq_item(2), mcq_item(3), mcq_item(4)]
    engine = GenerationEngine(groq_client=StubGroq(duplicated, unique))

    questions, report = await engine.generate(make_request(count=3))
    assert len(questions) == 3
    assert report.dropped_duplicates >= 1
    texts = [q.text for q in questions]
    assert len(set(texts)) == len(texts)


# --- error paths ---------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_marks_combination_raises_400():
    engine = GenerationEngine(groq_client=StubGroq([]))
    request = make_request(type=QuestionType.MCQ, marks=1).model_copy(
        update={"marks": 3}
    )
    with pytest.raises(InvalidRequestError):
        await engine.generate(request)


@pytest.mark.asyncio
async def test_unknown_chapter_raises_400_when_syllabus_supplied():
    syllabus = SyllabusIndex({Subject.SCIENCE: ["Nutrition in Plants"]})
    engine = GenerationEngine(groq_client=StubGroq([mcq_item(0)]), syllabus=syllabus)

    with pytest.raises(InvalidRequestError):
        await engine.generate(make_request(chapter="Quantum Chromodynamics"))

    # lookup is case- and punctuation-insensitive, so this one is accepted
    questions, _ = await engine.generate(
        make_request(chapter="nutrition in plants", count=1)
    )
    assert len(questions) == 1


@pytest.mark.asyncio
async def test_groq_failure_bubbles_as_502():
    engine = GenerationEngine(groq_client=StubGroq(GroqAPIError("upstream exploded")))
    with pytest.raises(GroqAPIError):
        await engine.generate(make_request())


@pytest.mark.asyncio
async def test_unfillable_batch_raises_422():
    broken = [{"text": "", "answer": ""}]
    engine = GenerationEngine(groq_client=StubGroq(broken))

    with pytest.raises(GenerationValidationError) as exc:
        await engine.generate(make_request(count=2))
    assert "0/2" in exc.value.detail


@pytest.mark.asyncio
async def test_rejection_reasons_are_fed_back_into_retry_prompt():
    bad = [{"text": "Explain photosynthesis.", "answer": "Because."}]
    good = [three_mark_item(i) for i in range(1)]
    stub = StubGroq(bad, good)
    engine = GenerationEngine(groq_client=stub)

    questions, report = await engine.generate(
        make_request(type=QuestionType.SHORT, marks=3, count=1)
    )
    assert len(questions) == 1
    assert report.attempts == 2
    # the second prompt should carry the first attempt's rejection reason
    second_prompt = stub.calls[1][1]
    assert "previous attempt was rejected" in second_prompt
    assert "3-mark answer" in second_prompt
