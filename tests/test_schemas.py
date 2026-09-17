import pytest
from pydantic import ValidationError

from generation_engine.schemas import Question, GenerationRequest, Subject, QuestionType, Difficulty


def make_mcq(**overrides):
    base = dict(
        subject=Subject.SCIENCE,
        chapter="Photosynthesis",
        type=QuestionType.MCQ,
        grade=8,
        text="What is the SI unit of force?",
        options=["Newton", "Joule", "Watt", "Pascal"],
        answer="Newton",
        explanation="Force is measured in Newtons per SI convention.",
        marks=1,
        difficulty=Difficulty.EASY,
        topic="Units",
    )
    base.update(overrides)
    return Question(**base)


def test_valid_mcq_builds():
    q = make_mcq()
    assert q.type == QuestionType.MCQ
    assert len(q.options) == 4


def test_mcq_requires_exactly_4_options():
    with pytest.raises(ValidationError):
        make_mcq(options=["Newton", "Joule", "Watt"])


def test_mcq_answer_must_be_one_of_options():
    with pytest.raises(ValidationError):
        make_mcq(answer="Kelvin")


def test_mcq_requires_justification():
    with pytest.raises(ValidationError):
        make_mcq(explanation="")


def test_mcq_must_be_1_mark():
    with pytest.raises(ValidationError):
        make_mcq(marks=2)


def test_non_mcq_cannot_carry_options():
    with pytest.raises(ValidationError):
        Question(
            subject=Subject.MATH,
            chapter="Algebra",
            type=QuestionType.SHORT,
            grade=8,
            text="Solve for x: 2x + 3 = 7",
            options=["1", "2", "3", "4"],
            answer="x = 2",
            marks=2,
            difficulty=Difficulty.EASY,
        )


@pytest.mark.parametrize(
    "qtype,valid_marks,invalid_mark",
    [
        (QuestionType.SHORT, {1, 2, 3}, 5),
        (QuestionType.LONG, {5}, 3),
    ],
)
def test_marks_must_match_type(qtype, valid_marks, invalid_mark):
    with pytest.raises(ValidationError):
        Question(
            subject=Subject.MATH,
            chapter="Algebra",
            type=qtype,
            grade=8,
            text="Explain the quadratic formula.",
            answer="Some answer",
            marks=invalid_mark,
            difficulty=Difficulty.MEDIUM,
        )
    # a valid mark from the allowed set should work
    ok_mark = sorted(valid_marks)[0]
    q = Question(
        subject=Subject.MATH,
        chapter="Algebra",
        type=qtype,
        grade=8,
        text="Explain the quadratic formula.",
        answer="Some answer",
        marks=ok_mark,
        difficulty=Difficulty.MEDIUM,
    )
    assert q.marks == ok_mark


def test_blank_text_rejected():
    with pytest.raises(ValidationError):
        make_mcq(text="   ")


def test_generation_request_count_bounds():
    with pytest.raises(ValidationError):
        GenerationRequest(
            subject=Subject.MATH,
            chapter="Algebra",
            type=QuestionType.MCQ,
            grade=8,
            marks=1,
            difficulty=Difficulty.EASY,
            count=0,
        )


# --- grade -----------------------------------------------------------------


@pytest.mark.parametrize("grade", [7, 8, 9])
def test_question_accepts_every_supported_grade(grade):
    q = make_mcq(grade=grade)
    assert q.grade == grade


@pytest.mark.parametrize("grade", [6, 10, 0, -1])
def test_question_rejects_out_of_range_grade(grade):
    with pytest.raises(ValidationError):
        make_mcq(grade=grade)


def test_question_requires_grade():
    with pytest.raises(ValidationError):
        make_mcq(grade=None)


def test_generation_request_accepts_every_supported_grade():
    for grade in (7, 8, 9):
        req = GenerationRequest(
            subject=Subject.MATH,
            chapter="Algebra",
            type=QuestionType.MCQ,
            grade=grade,
            marks=1,
            difficulty=Difficulty.EASY,
            count=1,
        )
        assert req.grade == grade


def test_generation_request_does_not_schema_validate_grade_range():
    # Mirrors `marks`: an out-of-range grade is accepted at construction and
    # is instead caught by validation.validate_request_combination() as a
    # 400 InvalidRequestError, not raised here as a pydantic ValidationError.
    req = GenerationRequest(
        subject=Subject.MATH,
        chapter="Algebra",
        type=QuestionType.MCQ,
        grade=12,
        marks=1,
        difficulty=Difficulty.EASY,
        count=1,
    )
    assert req.grade == 12
