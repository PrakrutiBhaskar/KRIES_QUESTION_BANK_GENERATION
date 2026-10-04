"""
Deterministic answer-key checks for Maths and Science.

The model that writes a question also writes its answer key, and it sometimes
gets the arithmetic or a standard fact wrong. For a narrow but common family
of questions the right answer can be computed or looked up, so this module
does that and compares it with the key. No LLM is involved.

The design rule is **precision over recall**: a check only fires when the
question matches a pattern strictly enough that the expected answer is
unambiguous. Anything else returns `NOT_APPLICABLE` and is left to the second
AI pass (see answer_verification.py). A false "mismatch" throws away a good
question, whereas a missed wrong key is still caught by the AI pass, so every
pattern here errs towards staying silent.

Outcomes (`RuleResult.outcome`):
  "ok"        the key agrees with the computed / known answer
  "mismatch"  the key disagrees; `detail` says what the right answer should be
  "na"        no rule applies, or the answer has nothing comparable in it

Maths:   arithmetic expressions, x% of n, square/cube roots and powers,
         LCM/HCF, one-variable linear equations, averages, simple interest,
         area/perimeter of rectangles, squares, triangles and circles,
         volume/surface area of cubes and cuboids.
Science: SI units, element symbols and atomic numbers, common chemical
         formulas, a few constants, and one-step physics formulas (speed,
         density, force, work, power, pressure, Ohm's law) with unit handling.
"""
from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass
from functools import reduce
from typing import Callable

from .schemas import Question, QuestionType, Subject


@dataclass(frozen=True)
class RuleResult:
    outcome: str  # "ok" | "mismatch" | "na"
    detail: str = ""


NOT_APPLICABLE = RuleResult("na")


def _ok(detail: str) -> RuleResult:
    return RuleResult("ok", detail)


def _mismatch(detail: str) -> RuleResult:
    return RuleResult("mismatch", detail)


# ---------------------------------------------------------------------------
# Numbers in an answer
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"(?<![\w.])-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
)
_FRACTION_RE = re.compile(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])")
_MIXED_RE = re.compile(r"(?<![\d.])(\d+)\s+(\d+)\s*/\s*(\d+)(?![\d.])")


def numbers_in(text: str) -> list[float]:
    """Every number an answer could be read as, including fractions."""
    t = text.replace("−", "-").replace("–", "-")
    values: list[float] = []
    for m in _MIXED_RE.finditer(t):
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if den:
            values.append(whole + num / den)
    for m in _FRACTION_RE.finditer(t):
        num, den = int(m.group(1)), int(m.group(2))
        if den:
            values.append(num / den)
    for m in _NUMBER_RE.finditer(t):
        values.append(float(m.group(0).replace(",", "")))
    return values


def _close(n: float, expected: float) -> bool:
    """Equal allowing for rounding.

    Accepts 0.5% either way, or the expected value rounded half-up or
    truncated to 0-2 decimal places (a key of 17 or 16 for 16.5 is a rounding
    convention, not a wrong answer; Python's own round() would reject 17).
    """
    if math.isclose(n, expected, rel_tol=5e-3, abs_tol=1e-9):
        return True
    for places in (0, 1, 2):
        scale = 10**places
        for candidate in (math.floor(expected * scale + 0.5) / scale, math.trunc(expected * scale) / scale):
            if math.isclose(n, candidate, abs_tol=1e-9):
                return True
    return False


def _any_close(values: list[float], expected: float) -> bool:
    return any(_close(v, expected) for v in values)


def _fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.6g}"


def _quote(answer: str, limit: int = 60) -> str:
    a = " ".join(answer.split())
    return a if len(a) <= limit else a[: limit - 1] + "…"


def _compare(q: Question, expected: float, how: str) -> RuleResult:
    """Compare the key's numbers with one expected value."""
    found = numbers_in(q.answer)
    if not found:
        return NOT_APPLICABLE
    if _any_close(found, expected):
        return _ok(f"Checked by calculation: {how} = {_fmt(expected)}.")
    return _mismatch(
        f"Calculation gives {_fmt(expected)} ({how}) but the answer key says "
        f"\"{_quote(q.answer)}\"."
    )


def _compare_any(q: Question, expected: list[float], how: str) -> RuleResult:
    """Like _compare, but several values are acceptable (e.g. unit variants)."""
    found = numbers_in(q.answer)
    if not found:
        return NOT_APPLICABLE
    if any(_any_close(found, e) for e in expected):
        return _ok(f"Checked by calculation: {how} = {_fmt(expected[0])}.")
    return _mismatch(
        f"Calculation gives {_fmt(expected[0])} ({how}) but the answer key says "
        f"\"{_quote(q.answer)}\"."
    )


# ---------------------------------------------------------------------------
# A tiny safe arithmetic evaluator (no eval())
# ---------------------------------------------------------------------------

_BINARY_OPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


class _Unsupported(Exception):
    pass


def _eval(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval(node.operand, env)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left, right = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Div) and right == 0:
            raise _Unsupported("division by zero")
        if isinstance(node.op, ast.Pow) and (abs(right) > 8 or abs(left) > 1e6):
            raise _Unsupported("power too large")
        return _BINARY_OPS[type(node.op)](left, right)
    raise _Unsupported(type(node).__name__)


def _evaluate(expr: str, env: dict[str, float] | None = None) -> float | None:
    if len(expr) > 120:
        return None
    try:
        value = _eval(ast.parse(expr.strip(), mode="eval"), env or {})
    except (SyntaxError, _Unsupported, ValueError, OverflowError, ZeroDivisionError):
        return None
    return value if math.isfinite(value) else None


def _normalise_math(s: str) -> str:
    s = (
        s.replace("×", "*")
        .replace("✕", "*")
        .replace("·", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("–", "-")
        .replace("²", "**2")
        .replace("³", "**3")
        .replace("^", "**")
    )
    return re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)


_ASK_VERBS = r"(?:what is|find|calculate|compute|evaluate|determine|simplify|solve)"


# ---------------------------------------------------------------------------
# Maths rules
# ---------------------------------------------------------------------------

_ARITH_RE = re.compile(
    rf"^\s*{_ASK_VERBS}(?:\s+the\s+value\s+of)?\s*:?\s*"
    r"(?P<expr>[\d\s+\-*/().×÷−xX^²³,]+?)\s*[?.=]*\s*$",
    re.I,
)


def _rule_arithmetic(q: Question) -> RuleResult:
    m = _ARITH_RE.match(q.text)
    if not m:
        return NOT_APPLICABLE
    if re.search(r"remainder|quotient", q.text + " " + q.answer, re.I):
        return NOT_APPLICABLE
    raw = m.group("expr")
    expr = _normalise_math(raw)
    expr = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", "*", expr)  # "12 x 5"
    expr = re.sub(r"(\d|\))\s*\(", r"\1*(", expr)  # 2(3+4)
    if len(re.findall(r"\d+(?:\.\d+)?", expr)) < 2 or not re.search(r"[-+*/]", expr):
        return NOT_APPLICABLE
    value = _evaluate(expr)
    if value is None:
        return NOT_APPLICABLE
    return _compare(q, value, " ".join(raw.split()))


_PERCENT_RE = re.compile(
    rf"^\s*{_ASK_VERBS}\s+(?:the\s+value\s+of\s+)?(?P<p>\d+(?:\.\d+)?)\s*%\s*of\s*"
    r"(?:rs\.?\s*|₹\s*)?(?P<n>\d+(?:,\d{3})*(?:\.\d+)?)\s*[?.]?\s*$",
    re.I,
)


def _rule_percent_of(q: Question) -> RuleResult:
    m = _PERCENT_RE.match(q.text)
    if not m:
        return NOT_APPLICABLE
    p, n = float(m.group("p")), float(m.group("n").replace(",", ""))
    return _compare(q, p * n / 100, f"{_fmt(p)}% of {_fmt(n)}")


_ROOT_RE = re.compile(
    rf"^\s*{_ASK_VERBS}\s+(?:the\s+)?(?P<kind>square|cube)\s+root\s+of\s+(?P<n>\d+)\s*[?.]?\s*$",
    re.I,
)
_SQRT_SYMBOL_RE = re.compile(
    rf"^\s*{_ASK_VERBS}\s+(?:the\s+value\s+of\s+)?(?P<kind>√|∛)\s*(?P<n>\d+)\s*[?.]?\s*$",
    re.I,
)
_POWER_RE = re.compile(
    rf"^\s*{_ASK_VERBS}\s+the\s+(?P<kind>square|cube)\s+of\s+(?P<n>\d+(?:\.\d+)?)\s*[?.]?\s*$",
    re.I,
)
_POWERED_RE = re.compile(
    rf"^\s*{_ASK_VERBS}\s+(?P<n>\d+(?:\.\d+)?)\s+(?P<kind>squared|cubed)\s*[?.]?\s*$",
    re.I,
)


def _rule_roots_and_powers(q: Question) -> RuleResult:
    for pattern in (_ROOT_RE, _SQRT_SYMBOL_RE):
        m = pattern.match(q.text)
        if m:
            n = int(m.group("n"))
            cube = m.group("kind").lower() in ("cube", "∛")
            root = round(n ** (1 / 3)) if cube else math.isqrt(n)
            if root ** (3 if cube else 2) != n:
                return NOT_APPLICABLE  # not a perfect power: the key may be a surd
            return _compare(q, float(root), f"{'cube' if cube else 'square'} root of {n}")
    for pattern in (_POWER_RE, _POWERED_RE):
        m = pattern.match(q.text)
        if m:
            n = float(m.group("n"))
            cube = m.group("kind").lower() in ("cube", "cubed")
            return _compare(q, n ** (3 if cube else 2), f"{_fmt(n)}{'³' if cube else '²'}")
    return NOT_APPLICABLE


_GCD_RE = re.compile(
    rf"^\s*{_ASK_VERBS}\s+the\s+(?P<what>lcm|hcf|gcd|l\.c\.m\.?|h\.c\.f\.?|g\.c\.d\.?|"
    r"least common multiple|highest common factor|greatest common (?:divisor|factor))"
    r"\s+of\s+(?P<nums>\d+(?:\s*(?:,|and|&)\s*\d+)+)\s*[?.]?\s*$",
    re.I,
)


def _rule_lcm_hcf(q: Question) -> RuleResult:
    m = _GCD_RE.match(q.text)
    if not m:
        return NOT_APPLICABLE
    nums = [int(n) for n in re.findall(r"\d+", m.group("nums"))]
    if not nums or 0 in nums:
        return NOT_APPLICABLE
    what = m.group("what").lower().replace(".", "")
    if what in ("lcm", "least common multiple"):
        value, label = reduce(math.lcm, nums), "LCM"
    else:
        value, label = reduce(math.gcd, nums), "HCF"
    return _compare(q, float(value), f"{label} of {', '.join(map(str, nums))}")


_AVERAGE_RE = re.compile(
    rf"^\s*{_ASK_VERBS}\s+the\s+(?:average|mean|arithmetic mean)\s+of\s+"
    r"(?P<nums>\d+(?:\.\d+)?(?:\s*(?:,|and|&)\s*\d+(?:\.\d+)?)+)\s*[?.]?\s*$",
    re.I,
)


def _rule_average(q: Question) -> RuleResult:
    m = _AVERAGE_RE.match(q.text)
    if not m:
        return NOT_APPLICABLE
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", m.group("nums"))]
    return _compare(q, sum(nums) / len(nums), f"average of {', '.join(_fmt(n) for n in nums)}")


_VAR = r"(?<![A-Za-z])[a-z](?![A-Za-z])"
_EQ_CHARS = rf"(?:[\d\s+\-*/().^²³×÷−]|{_VAR})"
_LEFT_RE = re.compile(rf"({_EQ_CHARS}+)$")
_RIGHT_RE = re.compile(rf"^({_EQ_CHARS}+)")
_SOLVE_INTENT_RE = re.compile(
    r"\b(solve|find the value of|find|determine|what is the value of|value of)\b", re.I
)


def _rule_linear_equation(q: Question) -> RuleResult:
    text = q.text
    if text.count("=") != 1 or not _SOLVE_INTENT_RE.search(text):
        return NOT_APPLICABLE
    left, right = text.split("=")
    lm = _LEFT_RE.search(left.rstrip(" ?:"))
    rm = _RIGHT_RE.match(right.lstrip())
    if not lm or not rm:
        return NOT_APPLICABLE
    lhs, rhs = lm.group(1).strip(), rm.group(1).strip().rstrip(" .")
    variables = set(re.findall(_VAR, lhs + " " + rhs))
    if len(variables) != 1:
        return NOT_APPLICABLE
    (var,) = variables
    # "x = 4" on its own is a given value, not an equation to solve, and in
    # "if x = 4, find 2x + 3" the target is something else entirely.
    if re.fullmatch(rf"\s*{var}\s*", lhs) or re.search(
        r"\b(when|where|given|substitute|put)\b", text, re.I
    ):
        return NOT_APPLICABLE
    if not re.search(
        rf"\bsolve\b|\b(?:find|determine|calculate|what is)\s+(?:the\s+value\s+of\s+)?(?:for\s+)?{var}\b",
        text,
        re.I,
    ):
        return NOT_APPLICABLE

    def prep(side: str) -> str:
        s = _normalise_math(side)
        s = re.sub(r"(\d|\))\s*([a-z(])", r"\1*\2", s)
        s = re.sub(rf"({var})\s*\(", r"\1*(", s)
        return s

    left_expr, right_expr = prep(lhs), prep(rhs)

    def f(x: float) -> float | None:
        a = _evaluate(left_expr, {var: x})
        b = _evaluate(right_expr, {var: x})
        return None if a is None or b is None else a - b

    f0, f1, f2 = f(0.0), f(1.0), f(2.0)
    if f0 is None or f1 is None or f2 is None:
        return NOT_APPLICABLE
    slope = f1 - f0
    if abs(slope) < 1e-12 or abs(f2 - 2 * f1 + f0) > 1e-9 * (1 + abs(f0) + abs(f1)):
        return NOT_APPLICABLE  # constant, or not linear in the variable
    solution = -f0 / slope
    return _compare(q, solution, f"{lhs} = {rhs} gives {var}")


_ASK_START_RE = re.compile(
    r"\b(?:calculate|find|determine|compute|what is|what will be|what was|how much|"
    r"how far|how long|state|evaluate)\b",
    re.I,
)
_PHRASE_END_RE = re.compile(
    r"\b(?:of|when|if|for|by|in|on|at|which|that|with|from|to|while|as|where|given|"
    r"is|are|across|through|after|before)\b|[,?.:;]",
    re.I,
)


def _asked_phrase(text: str) -> str:
    """The noun phrase right after the first ask-verb: 'the work done', 'the area'."""
    m = _ASK_START_RE.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    end = _PHRASE_END_RE.search(rest, 1)
    return (rest[: end.start()] if end else rest).strip().lower()


_NUM = r"(\d+(?:\.\d+)?)"


def _values(text: str, word: str) -> list[tuple[float, str]]:
    """(value, unit) for each `<word> ... <number> <unit>` in the text."""
    other = r"(?:length|breadth|width|side|radius|diameter|base|height|altitude|edge)"
    pattern = re.compile(
        rf"\b{word}s?\b(?:(?!\b{other}s?\b)[^\d.]){{0,25}}?{_NUM}\s*"
        r"(mm|cm|km|m|inch(?:es)?|ft|feet|units?)?\b",
        re.I,
    )
    return [(float(m.group(1)), (m.group(2) or "").lower()) for m in pattern.finditer(text)]


def _one(text: str, *words: str) -> tuple[float, str] | None:
    """The single value for any of these words, or None if absent / ambiguous."""
    found: list[tuple[float, str]] = []
    for w in words:
        found.extend(_values(text, w))
    return found[0] if len(found) == 1 else None


_GEOMETRY_EXCLUDE_RE = re.compile(
    r"\b(semi|quarter|half|sector|arc|ring|annulus|hollow|path|border|frame|"
    r"inscribed|circumscribed|ratio|similar|equilateral|isosceles|sphere|cylinder|cone)\b",
    re.I,
)


def _rule_geometry(q: Question) -> RuleResult:
    text = q.text
    if _GEOMETRY_EXCLUDE_RE.search(text):
        return NOT_APPLICABLE
    phrase = _asked_phrase(text)
    targets = {
        t
        for t, pat in (
            ("area", r"\barea\b"),
            ("perimeter", r"\bperimeter\b"),
            ("circumference", r"\bcircumference\b"),
            ("volume", r"\bvolume\b"),
            ("surface", r"\b(?:total\s+)?surface\s+area\b"),
        )
        if re.search(pat, phrase)
    }
    if "surface" in targets:
        targets.discard("area")
    if len(targets) != 1:
        return NOT_APPLICABLE
    (target,) = targets

    shapes = {
        s
        for s, pat in (
            ("rectangle", r"\brectang(?:le|ular)\b"),
            ("square", r"\bsquare\b(?!\s*(?:cm|centimet|m\b|metre|meter|km|unit|inch|feet|root))"),
            ("triangle", r"\btriangle\b"),
            ("circle", r"\bcircle\b|\bcircular\b"),
            ("cube", r"\bcube\b(?!\s+root)"),
            ("cuboid", r"\bcuboid\b|\brectangular\s+(?:box|solid|block)\b"),
        )
        if re.search(pat, text, re.I)
    }
    if len(shapes) != 1:
        return NOT_APPLICABLE
    (shape,) = shapes
    if shape == "rectangle" and "cuboid" in text.lower():
        return NOT_APPLICABLE

    def single(*words: str) -> float | None:
        got = _one(text, *words)
        return got[0] if got else None

    units = {u for w in ("length", "breadth", "width", "side", "radius", "diameter", "base", "height")
             for _, u in _values(text, w) if u}
    if len(units) > 1:
        return NOT_APPLICABLE

    value: float | None = None
    how = ""
    if shape == "rectangle" and target in ("area", "perimeter"):
        l, b = single("length"), single("breadth", "width")
        if l is None or b is None:
            return NOT_APPLICABLE
        value = l * b if target == "area" else 2 * (l + b)
        how = f"{target} of rectangle {_fmt(l)} × {_fmt(b)}"
    elif shape == "square" and target in ("area", "perimeter"):
        s = single("side")
        if s is None:
            return NOT_APPLICABLE
        value = s * s if target == "area" else 4 * s
        how = f"{target} of square with side {_fmt(s)}"
    elif shape == "triangle" and target == "area":
        base, h = single("base"), single("height", "altitude")
        if base is None or h is None:
            return NOT_APPLICABLE
        value = 0.5 * base * h
        how = f"½ × {_fmt(base)} × {_fmt(h)}"
    elif shape == "circle" and target in ("area", "circumference", "perimeter"):
        r, d = single("radius"), single("diameter")
        if (r is None) == (d is None):
            return NOT_APPLICABLE
        radius = r if r is not None else d / 2  # type: ignore[operator]
        value = math.pi * radius**2 if target == "area" else 2 * math.pi * radius
        how = f"{'area' if target == 'area' else 'circumference'} of circle with radius {_fmt(radius)}"
    elif shape == "cube" and target in ("volume", "surface"):
        s = single("side", "edge")
        if s is None:
            return NOT_APPLICABLE
        value = s**3 if target == "volume" else 6 * s**2
        how = f"{'volume' if target == 'volume' else 'surface area'} of cube with side {_fmt(s)}"
    elif shape == "cuboid" and target == "volume":
        l, b, h = single("length"), single("breadth", "width"), single("height")
        if l is None or b is None or h is None:
            return NOT_APPLICABLE
        value = l * b * h
        how = f"volume of cuboid {_fmt(l)} × {_fmt(b)} × {_fmt(h)}"
    if value is None:
        return NOT_APPLICABLE
    return _compare(q, value, how)


_CURRENCY_RE = re.compile(r"(?<![A-Za-z])(?:rs\.?|₹|inr)\s*(\d+(?:,\d{3})*(?:\.\d+)?)", re.I)
_RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(years?|yrs?|months?)\b", re.I)


def _rule_simple_interest(q: Question) -> RuleResult:
    text = q.text
    if not re.search(r"simple interest", text, re.I) or re.search(r"compound", text, re.I):
        return NOT_APPLICABLE
    phrase = _asked_phrase(text)
    wants_interest = "interest" in phrase
    wants_amount = bool(re.search(r"\bamount\b", phrase))
    if wants_interest == wants_amount:
        return NOT_APPLICABLE
    money, rate, time = _CURRENCY_RE.findall(text), _RATE_RE.findall(text), _TIME_RE.findall(text)
    if len(money) != 1 or len(rate) != 1 or len(time) != 1:
        return NOT_APPLICABLE
    principal = float(money[0].replace(",", ""))
    years = float(time[0][0]) / (12 if time[0][1].lower().startswith("month") else 1)
    interest = principal * float(rate[0]) * years / 100
    if wants_amount:
        return _compare(q, principal + interest, "principal + simple interest")
    return _compare(q, interest, "P × R × T / 100")


_MATH_RULES = (
    _rule_arithmetic,
    _rule_percent_of,
    _rule_roots_and_powers,
    _rule_lcm_hcf,
    _rule_average,
    _rule_linear_equation,
    _rule_simple_interest,
    _rule_geometry,
)


# ---------------------------------------------------------------------------
# Science: facts
# ---------------------------------------------------------------------------

_NEGATION_RE = re.compile(r"\b(not|except|incorrect|false|wrong|never)\b", re.I)

# quantity -> (spoken forms of the SI unit, symbol forms, extra spoken forms)
_SI_UNITS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "force": (("newton",), ("N", "kg m/s2", "kg m/s²", "kg·m/s²", "kg.m/s2")),
    "pressure": (("pascal",), ("Pa", "N/m2", "N/m²")),
    "work": (("joule",), ("J",)),
    "energy": (("joule",), ("J",)),
    "power": (("watt",), ("W", "J/s")),
    "frequency": (("hertz",), ("Hz",)),
    "electric current": (("ampere", "amp"), ("A",)),
    "current": (("ampere", "amp"), ("A",)),
    "potential difference": (("volt",), ("V",)),
    "voltage": (("volt",), ("V",)),
    "electric charge": (("coulomb",), ("C",)),
    "charge": (("coulomb",), ("C",)),
    "resistance": (("ohm",), ("Ω",)),
    "electrical resistance": (("ohm",), ("Ω",)),
    "length": (("metre", "meter"), ("m",)),
    "distance": (("metre", "meter"), ("m",)),
    "mass": (("kilogram",), ("kg",)),
    "time": (("second",), ("s",)),
    "temperature": (("kelvin",), ("K",)),
    "luminous intensity": (("candela",), ("cd",)),
    "amount of substance": (("mole",), ("mol",)),
    "speed": (("metre per second", "meter per second"), ("m/s", "m s-1")),
    "velocity": (("metre per second", "meter per second"), ("m/s", "m s-1")),
    "acceleration": (
        ("metre per second squared", "meter per second squared", "metre per second per second"),
        ("m/s2", "m/s²", "m s-2"),
    ),
    "density": (("kilogram per cubic metre", "kilogram per cubic meter"), ("kg/m3", "kg/m³")),
    "area": (("square metre", "square meter"), ("m2", "m²")),
    "volume": (("cubic metre", "cubic meter"), ("m3", "m³")),
    "momentum": (("kilogram metre per second", "kilogram meter per second"), ("kg m/s", "kg·m/s")),
    "capacitance": (("farad",), ("F",)),
    "magnetic field": (("tesla",), ("T",)),
    "inductance": (("henry",), ("H",)),
    "illuminance": (("lux",), ("lx",)),
}

# Names that identify *some* SI unit, so a wrong unit can be told apart from
# an answer phrased in a way this table doesn't know.
_ANY_UNIT_WORDS = {
    "newton", "pascal", "joule", "watt", "hertz", "ampere", "amp", "volt", "coulomb",
    "ohm", "metre", "meter", "kilogram", "second", "kelvin", "candela", "mole",
    "farad", "tesla", "henry", "lux", "calorie", "dyne", "erg", "bar", "atmosphere",
    "celsius", "fahrenheit",
}
_ALL_SI_SYMBOLS = {sym for _, symbols in _SI_UNITS.values() for sym in symbols}

_SI_UNIT_RE = re.compile(
    r"\bs\.?\s?i\.?\s+unit\s+(?:of|for)\s+(?:the\s+)?(?P<q>[a-z][a-z ]*?)\s*(?:\?|\.|:|$)",
    re.I,
)


def _has_symbol(answer: str, symbol: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9²³])", answer))


def _rule_si_unit(q: Question) -> RuleResult:
    if _NEGATION_RE.search(q.text):
        return NOT_APPLICABLE
    m = _SI_UNIT_RE.search(q.text)
    if not m:
        return NOT_APPLICABLE
    quantity = re.sub(r"\s+(?:is|are|will be)$", "", " ".join(m.group("q").lower().split()))
    entry = _SI_UNITS.get(quantity)
    if entry is None:
        return NOT_APPLICABLE
    words, symbols = entry
    answer = q.answer
    lowered = answer.lower()
    if any(re.search(rf"\b{re.escape(w)}s?\b", lowered) for w in words) or any(
        _has_symbol(answer, s) for s in symbols
    ):
        return _ok(f"Checked against known facts: the SI unit of {quantity} is the {words[0]}.")
    bare = answer.strip().strip(".")
    if any(re.search(rf"\b{w}s?\b", lowered) for w in _ANY_UNIT_WORDS) or bare in _ALL_SI_SYMBOLS:
        return _mismatch(
            f"The SI unit of {quantity} is the {words[0]} ({symbols[0]}), "
            f"but the answer key says \"{_quote(answer)}\"."
        )
    return NOT_APPLICABLE


# name -> (symbol, atomic number); only elements a Class 7-9 syllabus uses
_ELEMENTS: dict[str, tuple[str, int]] = {
    "hydrogen": ("H", 1), "helium": ("He", 2), "lithium": ("Li", 3), "beryllium": ("Be", 4),
    "boron": ("B", 5), "carbon": ("C", 6), "nitrogen": ("N", 7), "oxygen": ("O", 8),
    "fluorine": ("F", 9), "neon": ("Ne", 10), "sodium": ("Na", 11), "magnesium": ("Mg", 12),
    "aluminium": ("Al", 13), "aluminum": ("Al", 13), "silicon": ("Si", 14),
    "phosphorus": ("P", 15), "sulphur": ("S", 16), "sulfur": ("S", 16), "chlorine": ("Cl", 17),
    "argon": ("Ar", 18), "potassium": ("K", 19), "calcium": ("Ca", 20), "iron": ("Fe", 26),
    "copper": ("Cu", 29), "zinc": ("Zn", 30), "silver": ("Ag", 47), "tin": ("Sn", 50),
    "iodine": ("I", 53), "gold": ("Au", 79), "mercury": ("Hg", 80), "lead": ("Pb", 82),
}
_SYMBOL_TO_NAMES: dict[str, set[str]] = {}
for _name, (_sym, _) in _ELEMENTS.items():
    _SYMBOL_TO_NAMES.setdefault(_sym, set()).add(_name)

_SYMBOL_OF_RE = re.compile(
    r"\b(?:chemical\s+)?symbol\s+(?:of|for)\s+(?:the\s+element\s+)?(?P<e>[a-z]+)\b", re.I
)
_ATOMIC_NUMBER_RE = re.compile(
    r"\batomic\s+number\s+of\s+(?:the\s+element\s+)?(?P<e>[a-z]+)\b", re.I
)
_WHICH_ELEMENT_RE = re.compile(
    r"(?i:\bwhich\s+element\b).*\bsymbol\s+(?P<s>[A-Z][a-z]?)\b|"
    r"\belement\s+(?:with|having)\s+(?:the\s+)?(?:chemical\s+)?symbol\s+(?P<s2>[A-Z][a-z]?)\b"
)


def _rule_elements(q: Question) -> RuleResult:
    if _NEGATION_RE.search(q.text):
        return NOT_APPLICABLE
    m = _ATOMIC_NUMBER_RE.search(q.text)
    if m and m.group("e").lower() in _ELEMENTS:
        name = m.group("e").lower()
        expected = _ELEMENTS[name][1]
        found = numbers_in(q.answer)
        if not found:
            return NOT_APPLICABLE
        if expected in [int(v) for v in found if v == int(v)]:
            return _ok(f"Checked against known facts: the atomic number of {name} is {expected}.")
        return _mismatch(
            f"The atomic number of {name} is {expected}, but the answer key says "
            f"\"{_quote(q.answer)}\"."
        )
    m = _SYMBOL_OF_RE.search(q.text)
    if m and m.group("e").lower() in _ELEMENTS:
        name = m.group("e").lower()
        symbol = _ELEMENTS[name][0]
        if _has_symbol(q.answer, symbol) and not re.search(
            rf"(?<![A-Za-z]){re.escape(symbol)}[a-z]", q.answer
        ):
            return _ok(f"Checked against known facts: the symbol of {name} is {symbol}.")
        if re.search(r"(?<![A-Za-z])[A-Z][a-z]?(?![A-Za-z])", q.answer):
            return _mismatch(
                f"The symbol of {name} is {symbol}, but the answer key says "
                f"\"{_quote(q.answer)}\"."
            )
        return NOT_APPLICABLE
    m = _WHICH_ELEMENT_RE.search(q.text)
    if m:
        symbol = m.group("s") or m.group("s2")
        names = _SYMBOL_TO_NAMES.get(symbol)
        if not names:
            return NOT_APPLICABLE
        lowered = q.answer.lower()
        if any(re.search(rf"\b{n}\b", lowered) for n in names):
            return _ok(f"Checked against known facts: {symbol} is {sorted(names)[0]}.")
        if any(re.search(rf"\b{n}\b", lowered) for n in _ELEMENTS):
            return _mismatch(
                f"{symbol} is {sorted(names)[0]}, but the answer key says \"{_quote(q.answer)}\"."
            )
    return NOT_APPLICABLE


_FORMULAS: dict[str, str] = {
    "water": "H2O", "carbon dioxide": "CO2", "carbon monoxide": "CO",
    "common salt": "NaCl", "table salt": "NaCl", "sodium chloride": "NaCl",
    "ammonia": "NH3", "methane": "CH4", "ozone": "O3", "hydrogen peroxide": "H2O2",
    "sulphuric acid": "H2SO4", "sulfuric acid": "H2SO4", "hydrochloric acid": "HCl",
    "nitric acid": "HNO3", "sodium hydroxide": "NaOH", "calcium carbonate": "CaCO3",
    "calcium oxide": "CaO", "quicklime": "CaO", "slaked lime": "Ca(OH)2",
    "calcium hydroxide": "Ca(OH)2", "glucose": "C6H12O6", "baking soda": "NaHCO3",
    "sodium bicarbonate": "NaHCO3", "sodium hydrogen carbonate": "NaHCO3",
    "washing soda": "Na2CO3", "sodium carbonate": "Na2CO3", "ethanol": "C2H5OH",
}
_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_FORMULA_RE = re.compile(
    r"\b(?:chemical|molecular)\s+formula\s+(?:of|for)\s+(?:the\s+)?(?:compound\s+)?"
    r"(?P<c>[a-z][a-z ]*?)\s*(?:\?|\.|:|$)",
    re.I,
)


def _rule_formulas(q: Question) -> RuleResult:
    if _NEGATION_RE.search(q.text):
        return NOT_APPLICABLE
    m = _FORMULA_RE.search(q.text)
    if not m:
        return NOT_APPLICABLE
    name = " ".join(m.group("c").lower().split())
    expected = _FORMULAS.get(name)
    if expected is None:
        return NOT_APPLICABLE
    answer = q.answer.translate(_SUBSCRIPTS).replace(" ", "")
    pattern = rf"(?<![A-Za-z0-9]){re.escape(expected)}(?![a-z0-9(])"
    if re.search(pattern, answer):
        return _ok(f"Checked against known facts: the formula of {name} is {expected}.")
    if re.search(r"[A-Z][a-z]?\d*", answer):
        return _mismatch(
            f"The formula of {name} is {expected}, but the answer key says \"{_quote(q.answer)}\"."
        )
    return NOT_APPLICABLE


_CONSTANT_RULES: tuple[tuple[re.Pattern[str], list[float], str], ...] = (
    (
        re.compile(
            r"^\s*(?:what is|state|write)\s+the\s+(?:value\s+of\s+)?"
            r"(?:acceleration\s+due\s+to\s+gravity|g)(?:\s+on\s+(?:the\s+)?earth)?"
            r"(?:'s surface)?\s*[?.]?\s*$",
            re.I,
        ),
        [9.8, 9.81, 9.80665, 10.0],
        "acceleration due to gravity on Earth (9.8 m/s², or 10 m/s² as often rounded)",
    ),
    (
        re.compile(
            r"^\s*(?:what is|state|write)\s+the\s+boiling\s+point\s+of\s+(?:pure\s+)?water"
            r"(?:\s+at\s+(?:standard|normal)\s+(?:atmospheric\s+)?pressure)?\s*[?.]?\s*$",
            re.I,
        ),
        [100.0, 373.0, 373.15, 212.0],
        "boiling point of water (100 °C = 373 K = 212 °F)",
    ),
    (
        re.compile(
            r"^\s*(?:what is|state|write)\s+the\s+(?:freezing|melting)\s+point\s+of\s+"
            r"(?:pure\s+)?(?:water|ice)\s*[?.]?\s*$",
            re.I,
        ),
        [0.0, 273.0, 273.15, 32.0],
        "freezing point of water (0 °C = 273 K = 32 °F)",
    ),
)


def _rule_constants(q: Question) -> RuleResult:
    for pattern, accepted, label in _CONSTANT_RULES:
        if pattern.match(q.text):
            found = numbers_in(q.answer)
            if not found:
                return NOT_APPLICABLE
            if any(_any_close(found, a) for a in accepted):
                return _ok(f"Checked against known facts: {label}.")
            return _mismatch(f"Known value: {label}, but the answer key says \"{_quote(q.answer)}\".")
    return NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Science: one-step physics formulas
# ---------------------------------------------------------------------------

# symbol -> (kind, factor to the SI base unit). Letter-only symbols are
# case-sensitive so "5 a day" is never read as 5 amperes.
_SYMBOL_UNITS: dict[str, tuple[str, float]] = {
    "mm": ("length", 1e-3), "cm": ("length", 1e-2), "m": ("length", 1.0), "km": ("length", 1e3),
    "mg": ("mass", 1e-6), "g": ("mass", 1e-3), "kg": ("mass", 1.0),
    "s": ("time", 1.0), "min": ("time", 60.0), "h": ("time", 3600.0), "hr": ("time", 3600.0),
    "N": ("force", 1.0), "kN": ("force", 1e3),
    "J": ("energy", 1.0), "kJ": ("energy", 1e3),
    "W": ("power", 1.0), "kW": ("power", 1e3),
    "A": ("current", 1.0), "mA": ("current", 1e-3),
    "V": ("voltage", 1.0), "kV": ("voltage", 1e3), "mV": ("voltage", 1e-3),
    "Ω": ("resistance", 1.0), "kΩ": ("resistance", 1e3),
    "Pa": ("pressure", 1.0), "kPa": ("pressure", 1e3),
    "m/s": ("speed", 1.0), "km/h": ("speed", 1 / 3.6), "cm/s": ("speed", 1e-2),
    "m/s²": ("acceleration", 1.0), "m/s2": ("acceleration", 1.0), "m/s^2": ("acceleration", 1.0),
    "m²": ("area", 1.0), "m2": ("area", 1.0), "cm²": ("area", 1e-4), "cm2": ("area", 1e-4),
    "m³": ("volume", 1.0), "m3": ("volume", 1.0), "cm³": ("volume", 1e-6),
    "cm3": ("volume", 1e-6), "cc": ("volume", 1e-6), "L": ("volume", 1e-3), "ml": ("volume", 1e-6),
    "mL": ("volume", 1e-6),
    "kg/m³": ("density", 1.0), "kg/m3": ("density", 1.0),
    "g/cm³": ("density", 1e3), "g/cm3": ("density", 1e3), "g/cc": ("density", 1e3),
}
_WORD_UNITS: dict[str, tuple[str, float]] = {
    "millimetre": ("length", 1e-3), "millimeter": ("length", 1e-3),
    "centimetre": ("length", 1e-2), "centimeter": ("length", 1e-2),
    "metre": ("length", 1.0), "meter": ("length", 1.0),
    "kilometre": ("length", 1e3), "kilometer": ("length", 1e3),
    "gram": ("mass", 1e-3), "kilogram": ("mass", 1.0),
    "second": ("time", 1.0), "sec": ("time", 1.0), "minute": ("time", 60.0),
    "hour": ("time", 3600.0),
    "newton": ("force", 1.0), "joule": ("energy", 1.0), "watt": ("power", 1.0),
    "ampere": ("current", 1.0), "amp": ("current", 1.0), "volt": ("voltage", 1.0),
    "ohm": ("resistance", 1.0), "pascal": ("pressure", 1.0),
    "litre": ("volume", 1e-3), "liter": ("volume", 1e-3),
}

_symbol_alt = "|".join(re.escape(s) for s in sorted(_SYMBOL_UNITS, key=len, reverse=True))
_word_alt = "|".join(sorted(_WORD_UNITS, key=len, reverse=True))
_QUANTITY_RE = re.compile(
    rf"(?<![\w.^/])(?P<num>\d+(?:,\d{{3}})*(?:\.\d+)?)\s*"
    rf"(?:(?P<sym>{_symbol_alt})|(?P<word>(?i:{_word_alt})s?))(?![A-Za-z0-9²³^/])"
)


def _quantities(text: str) -> dict[str, list[float]]:
    """Every `<number> <unit>` in the text, converted to SI, grouped by kind."""
    out: dict[str, list[float]] = {}
    for m in _QUANTITY_RE.finditer(text):
        number = float(m.group("num").replace(",", ""))
        if m.group("sym"):
            kind, factor = _SYMBOL_UNITS[m.group("sym")]
        else:
            word = m.group("word").lower()
            word = word[:-1] if word.endswith("s") and word[:-1] in _WORD_UNITS else word
            kind, factor = _WORD_UNITS[word]
        out.setdefault(kind, []).append(number * factor)
    return out


# target -> (phrase pattern, [(needed kinds, formula)], result unit factors)
_PHYSICS: dict[str, tuple[str, list[tuple[tuple[str, ...], Callable[..., float], str]], list[float]]] = {
    "speed": (
        r"\b(?:average\s+)?speed\b|\bvelocity\b",
        [(("length", "time"), lambda length, time: length / time, "distance ÷ time")],
        [1.0, 3.6, 100.0, 60.0],  # m/s, km/h, cm/s, m/min
    ),
    "density": (
        r"\bdensity\b",
        [(("mass", "volume"), lambda mass, volume: mass / volume, "mass ÷ volume")],
        [1.0, 1e-3],  # kg/m³, g/cm³
    ),
    "force": (
        r"\bforce\b",
        [(("mass", "acceleration"), lambda mass, acceleration: mass * acceleration, "mass × acceleration")],
        [1.0, 1e-3],
    ),
    "work": (
        r"\bwork(?:\s+done)?\b",
        [(("force", "length"), lambda force, length: force * length, "force × distance")],
        [1.0, 1e-3],
    ),
    "power": (
        r"\bpower\b",
        [
            (("energy", "time"), lambda energy, time: energy / time, "work ÷ time"),
            (("voltage", "current"), lambda voltage, current: voltage * current, "V × I"),
        ],
        [1.0, 1e-3],
    ),
    "pressure": (
        r"\bpressure\b",
        [(("force", "area"), lambda force, area: force / area, "force ÷ area")],
        [1.0, 1e-3],
    ),
    "current": (
        r"\bcurrent\b",
        [(("voltage", "resistance"), lambda voltage, resistance: voltage / resistance, "V ÷ R")],
        [1.0, 1e3],
    ),
    "resistance": (
        r"\bresistance\b",
        [(("voltage", "current"), lambda voltage, current: voltage / current, "V ÷ I")],
        [1.0, 1e-3],
    ),
    "voltage": (
        r"\b(?:potential\s+difference|voltage|emf)\b",
        [(("current", "resistance"), lambda current, resistance: current * resistance, "I × R")],
        [1.0, 1e-3, 1e3],
    ),
}


def _rule_physics(q: Question) -> RuleResult:
    phrase = _asked_phrase(q.text)
    if not phrase:
        return NOT_APPLICABLE
    targets = [t for t, (pat, _, _) in _PHYSICS.items() if re.search(pat, phrase)]
    if len(targets) != 1:
        return NOT_APPLICABLE
    target = targets[0]
    _, formulas, factors = _PHYSICS[target]
    quantities = _quantities(q.text)
    for needed, formula, how in formulas:
        if all(len(quantities.get(kind, [])) == 1 for kind in needed):
            args = [quantities[kind][0] for kind in needed]
            if any(a == 0 for a in args) and "÷" in how:
                return NOT_APPLICABLE
            try:
                value = formula(*args)
            except ZeroDivisionError:
                return NOT_APPLICABLE
            return _compare_any(q, [value * f for f in factors], f"{target} = {how}")
    return NOT_APPLICABLE


_SCIENCE_RULES = (
    _rule_si_unit,
    _rule_elements,
    _rule_formulas,
    _rule_constants,
    _rule_physics,
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def check_answer_rules(question: Question) -> RuleResult:
    """Run every rule for the question's subject; the first that applies wins."""
    if question.type == QuestionType.MATCH:
        # Two columns of text, not a calculation or a single fact: nothing here
        # is safe to compute, so leave it to the AI pass.
        return NOT_APPLICABLE
    if question.subject == Subject.MATH:
        rules = _MATH_RULES
    elif question.subject == Subject.SCIENCE:
        rules = _SCIENCE_RULES
    else:
        return NOT_APPLICABLE
    for rule in rules:
        result = rule(question)
        if result.outcome != "na":
            return result
    return NOT_APPLICABLE
