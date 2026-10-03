"""Rule checks for Maths and Science answer keys (generation_engine/rule_checks.py).

The table is the contract: every row is (question, answer key, subject, expected
outcome). "na" rows matter as much as the others: they are the false-positive
guards, cases that look checkable but must be left alone.
"""
from __future__ import annotations

import pytest

from generation_engine.rule_checks import check_answer_rules, numbers_in
from generation_engine.schemas import Difficulty, Question, QuestionType, Subject

MATH, SCI = Subject.MATH, Subject.SCIENCE


def make(text, answer, subject=MATH, mcq=False):
    kwargs = dict(
        subject=subject, chapter="c", type=QuestionType.SHORT, grade=8,
        text=text, answer=answer, marks=1, difficulty=Difficulty.EASY,
    )
    if mcq:
        kwargs.update(
            type=QuestionType.MCQ, explanation="because",
            options=[answer, "decoy one 1", "decoy two 2", "decoy three 3"],
        )
    return Question(**kwargs)


CASES = [
    # --- Maths: arithmetic -------------------------------------------------
    ("What is 12 × 15?", "180", MATH, "ok"),
    ("What is 12 × 15?", "170", MATH, "mismatch"),
    ("What is 12 x 15?", "180", MATH, "ok"),
    ("Evaluate 3/4 + 1/2", "5/4", MATH, "ok"),
    ("Evaluate 3/4 + 1/2", "1 1/4", MATH, "ok"),
    ("Calculate 2 + 3 × 4", "14", MATH, "ok"),
    ("Calculate 2 + 3 × 4", "20", MATH, "mismatch"),  # precedence
    ("Calculate (2 + 3) × 4", "20", MATH, "ok"),
    ("What is 0.5 × 0.4?", "0.2", MATH, "ok"),
    ("What is 2^3 × 5?", "40", MATH, "ok"),
    ("What is 8 ÷ 3?", "2.67", MATH, "ok"),
    ("What is 17 ÷ 5?", "3 remainder 2", MATH, "na"),
    ("What is 5 + x?", "7", MATH, "na"),
    ("What is 7?", "7", MATH, "na"),
    ("What is 7 - 3 in binary?", "100", MATH, "na"),
    ("Simplify 3x + 2x", "5x", MATH, "na"),
    # --- Maths: percent, roots, powers, LCM/HCF, average --------------------
    ("What is 25% of 240?", "60", MATH, "ok"),
    ("Find 15% of 200", "40", MATH, "mismatch"),
    ("Find the square root of 144.", "12", MATH, "ok"),
    ("Find the square root of 144.", "14", MATH, "mismatch"),
    ("Find the square root of 50.", "5√2", MATH, "na"),
    ("What is the cube root of 27?", "3", MATH, "ok"),
    ("What is the cube of 4?", "64", MATH, "ok"),
    ("Find the cube of 4", "12", MATH, "mismatch"),
    ("What is 7 squared?", "49", MATH, "ok"),
    ("Find the HCF of 12 and 18.", "6", MATH, "ok"),
    ("Find the HCF of 12 and 18.", "3", MATH, "mismatch"),
    ("Find the LCM of 4, 6 and 10", "60", MATH, "ok"),
    ("Find the LCM of 4, 6 and 10", "30", MATH, "mismatch"),
    ("Find the average of 12, 15, 18 and 21", "16.5", MATH, "ok"),
    ("Find the average of 12, 15, 18 and 21", "17", MATH, "ok"),  # within rounding
    ("Find the average of 12, 15, 18 and 21", "18.5", MATH, "mismatch"),
    # --- Maths: linear equations --------------------------------------------
    ("Solve 2x + 5 = 15", "x = 5", MATH, "ok"),
    ("Solve 2x + 5 = 15", "x = 10", MATH, "mismatch"),
    ("Find the value of x if 3x - 4 = 11", "5", MATH, "ok"),
    ("Solve for x: (x + 3)/2 = 7", "11", MATH, "ok"),
    ("Solve 3(y - 2) = 12", "y = 6", MATH, "ok"),
    ("Find x if x/4 = 3", "12", MATH, "ok"),
    ("If x = 4, find 2x + 3", "11", MATH, "na"),  # substitution, not an equation
    ("Find the value of 2x + 3 when x = 4", "11", MATH, "na"),
    ("Solve x^2 = 9", "3", MATH, "na"),  # not linear
    ("Solve x + y = 10", "5", MATH, "na"),  # two unknowns
    ("Solve x + 1 = x + 2", "none", MATH, "na"),  # no solution
    # --- Maths: simple interest ----------------------------------------------
    ("Find the simple interest on ₹5,000 at 8% per annum for 3 years.", "₹1,200", MATH, "ok"),
    ("Find the simple interest on ₹5,000 at 8% per annum for 3 years.", "₹1,500", MATH, "mismatch"),
    ("Find the amount on ₹5,000 at 8% per annum simple interest for 3 years.", "₹6,200", MATH, "ok"),
    ("Find the simple interest and the amount on ₹5,000 at 8% for 3 years.", "1200", MATH, "na"),
    ("Find the simple interest on ₹5,000 at 8% per annum for 6 months.", "₹200", MATH, "ok"),
    ("Find the compound interest on ₹5,000 at 8% per annum for 2 years.", "₹832", MATH, "na"),
    # --- Maths: geometry --------------------------------------------------------
    ("Find the area of a rectangle with length 8 cm and breadth 5 cm.", "40 cm²", MATH, "ok"),
    ("Find the area of a rectangle with length 8 cm and breadth 5 cm.", "26 cm²", MATH, "mismatch"),
    ("Find the perimeter of a rectangle of length 8 cm and breadth 5 cm.", "26 cm", MATH, "ok"),
    ("Find the area of a square of side 7 cm.", "49 square cm", MATH, "ok"),
    ("Find the perimeter of a square of side 7 cm.", "28 cm", MATH, "ok"),
    ("Calculate the area of a circle with radius 7 cm.", "154 cm²", MATH, "ok"),
    ("Calculate the area of a circle with radius 7 cm.", "44 cm²", MATH, "mismatch"),
    ("Find the circumference of a circle with diameter 14 cm.", "44 cm", MATH, "ok"),
    ("Find the area of a triangle with base 10 cm and height 6 cm.", "30 cm²", MATH, "ok"),
    ("Find the volume of a cube of side 3 cm.", "27 cm³", MATH, "ok"),
    ("Find the total surface area of a cube of side 3 cm.", "54 cm²", MATH, "ok"),
    ("Find the volume of a cuboid with length 4 cm, breadth 3 cm and height 2 cm.", "24 cm³", MATH, "ok"),
    ("Find the area of a semicircle with radius 7 cm.", "77 cm²", MATH, "na"),
    ("Find the area of a rectangle with length 8 cm and breadth 5 m.", "40", MATH, "na"),  # mixed units
    ("Find the area and perimeter of a rectangle with length 8 cm and breadth 5 cm.", "40", MATH, "na"),
    ("Find the area of a rectangle with length l and breadth 5 cm.", "25", MATH, "na"),  # l unknown
    # --- Science: facts ---------------------------------------------------------
    ("What is the SI unit of force?", "Newton", SCI, "ok"),
    ("What is the SI unit of force?", "newton (N)", SCI, "ok"),
    ("What is the SI unit of force?", "Joule", SCI, "mismatch"),
    ("What is the SI unit of force?", "J", SCI, "mismatch"),
    ("Which of the following is the SI unit of pressure?", "Pascal", SCI, "ok"),
    ("What is the SI unit of electric current?", "Ampere", SCI, "ok"),
    ("What is the SI unit of temperature?", "Kelvin", SCI, "ok"),
    ("What is the SI unit of temperature?", "Celsius", SCI, "mismatch"),
    ("Which is NOT the SI unit of force?", "Joule", SCI, "na"),  # negated stem
    ("What is the SI unit of work done?", "Joule", SCI, "na"),  # not in the table
    ("What is the chemical symbol for sodium?", "Na", SCI, "ok"),
    ("What is the chemical symbol for sodium?", "So", SCI, "mismatch"),
    ("What is the chemical symbol of nitrogen?", "Na", SCI, "mismatch"),
    ("What is the chemical symbol of nitrogen?", "N", SCI, "ok"),
    ("What is the atomic number of carbon?", "6", SCI, "ok"),
    ("What is the atomic number of carbon?", "12", SCI, "mismatch"),
    ("Which element has the chemical symbol Fe?", "Iron", SCI, "ok"),
    ("Which element has the chemical symbol Fe?", "Copper", SCI, "mismatch"),
    ("What is the chemical formula of water?", "H₂O", SCI, "ok"),
    ("What is the chemical formula of water?", "H2O2", SCI, "mismatch"),
    ("What is the chemical formula of carbon dioxide?", "CO", SCI, "mismatch"),
    ("What is the chemical formula of carbon monoxide?", "CO2", SCI, "mismatch"),
    ("What is the chemical formula of carbon monoxide?", "CO", SCI, "ok"),
    ("What is the chemical formula of calcium hydroxide?", "Ca(OH)₂", SCI, "ok"),
    ("What is the boiling point of water?", "100 °C", SCI, "ok"),
    ("What is the boiling point of water?", "373 K", SCI, "ok"),
    ("What is the boiling point of water?", "90 °C", SCI, "mismatch"),
    ("What is the boiling point of water on the top of Mount Everest?", "71 °C", SCI, "na"),
    ("What is the value of g on Earth?", "9.8 m/s²", SCI, "ok"),
    # --- Science: one-step physics ----------------------------------------------
    ("A car travels 150 km in 3 hours. Find its average speed.", "50 km/h", SCI, "ok"),
    ("A car travels 150 km in 3 hours. Find its average speed.", "13.9 m/s", SCI, "ok"),
    ("A car travels 150 km in 3 hours. Find its average speed.", "60 km/h", SCI, "mismatch"),
    ("A car covers 60 km in 1 hour and then 40 km in 1 hour. Find its average speed.", "50", SCI, "na"),
    ("Calculate the force required to accelerate a 5 kg mass at 2 m/s².", "10 N", SCI, "ok"),
    ("Calculate the force required to accelerate a 5 kg mass at 2 m/s².", "7 N", SCI, "mismatch"),
    ("Calculate the work done when a force of 10 N moves a body through 5 m.", "50 J", SCI, "ok"),
    ("Find the power of a machine that does 500 J of work in 10 s.", "50 W", SCI, "ok"),
    ("Find the power of a machine that does 500 J of work in 10 s.", "5000 W", SCI, "mismatch"),
    ("What is the potential difference across a 10 Ω resistor carrying 2 A?", "20 V", SCI, "ok"),
    ("What is the potential difference across a 10 Ω resistor carrying 2 A?", "5 V", SCI, "mismatch"),
    ("Find the current in a circuit with voltage 12 V and resistance 4 Ω.", "3 A", SCI, "ok"),
    ("Find the resistance of a conductor with voltage 12 V and current 3 A.", "4 Ω", SCI, "ok"),
    ("Calculate the pressure exerted by a force of 100 N on an area of 2 m².", "50 Pa", SCI, "ok"),
    ("Calculate the density of a substance of mass 500 g and volume 250 cm³.", "2 g/cm³", SCI, "ok"),
    ("Calculate the density of a substance of mass 500 g and volume 250 cm³.", "2000 kg/m³", SCI, "ok"),
    ("Calculate the density of a substance of mass 500 g and volume 250 cm³.", "5 g/cm³", SCI, "mismatch"),
    ("Find the momentum of a 5 kg body moving at 10 m/s.", "50", SCI, "na"),  # no rule
    ("Calculate the force when pressure is 10 Pa on an area of 2 m².", "20 N", SCI, "na"),  # other formula
    ("Why does a ball stop rolling?", "Friction", SCI, "na"),
    # --- Other subjects are never rule-checked -----------------------------------
    ("What is 2 + 2?", "5", Subject.SOCIAL_SCIENCE, "na"),
    ("What is 2 + 2?", "5", Subject.ENGLISH, "na"),
]


@pytest.mark.parametrize("text,answer,subject,expected", CASES)
def test_rule_outcome(text, answer, subject, expected):
    result = check_answer_rules(make(text, answer, subject))
    assert result.outcome == expected, (text, answer, result)
    if expected == "na":
        assert result.detail == ""
    else:
        assert result.detail  # always explains itself


def test_mismatch_detail_states_the_right_answer_and_the_key():
    result = check_answer_rules(make("What is 12 × 15?", "170"))
    assert "180" in result.detail and "170" in result.detail


def test_works_on_mcq_options():
    assert check_answer_rules(make("What is 12 × 15?", "180", mcq=True)).outcome == "ok"
    assert check_answer_rules(make("What is 12 × 15?", "170", mcq=True)).outcome == "mismatch"


def test_an_answer_with_no_number_is_left_alone():
    assert check_answer_rules(make("What is 12 × 15?", "one hundred and eighty")).outcome == "na"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("180", [180.0]),
        ("1,200", [1200.0]),
        ("₹1,200.50", [1200.5]),
        ("x = -5", [-5.0]),
        ("3/4", [0.75, 3.0, 4.0]),
        ("1 3/4", [1.75, 0.75, 1.0, 3.0, 4.0]),
        ("40cm²", [40.0]),
        ("H2O", []),
        ("2-3", [2.0, 3.0]),
        ("5, 6, 7", [5.0, 6.0, 7.0]),
    ],
)
def test_numbers_in(text, expected):
    assert sorted(numbers_in(text)) == sorted(expected)


def test_never_raises_on_odd_input():
    odd = [
        "What is 1 ÷ 0?", "What is 99999999999 ^ 99999?", "Solve = =", "What is ((((((1+1",
        "Find the average of 1 and 1", "Find the HCF of 0 and 5.", "What is 5 +", "Solve 0x = 0",
    ]
    for text in odd:
        check_answer_rules(make(text, "1"))
