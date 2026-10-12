"""Optiver-style 80 in 8 (unofficial practice format): 80 multiple-choice questions, mixed decimals & fractions,
percentages and core arithmetic at MEDIUM–HARD. Each has 4 distinct options, exactly one right; the other three
are plausible near-misses. Pure Python, exact arithmetic."""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction

from met_games.games.math.problems import (
    CORE,
    DECFRAC,
    FRACTION,
    HARD,
    MEDIUM,
    PCT,
    Problem,
    dec,
    frac,
    make,
    places,
)

QUESTIONS = 80
OPTIONS = 4
FAMILY_CYCLE = (DECFRAC, PCT, CORE)
SIGNED = ("pct_change", "chained", "pnl")  # subtypes whose answers can be negative


@dataclass(frozen=True)
class Question:
    problem: Problem
    options: tuple[str, ...]
    correct: int  # index of the right option


def show(p: Problem, x: Fraction) -> str:
    return frac(x) if p.form == FRACTION else dec(x)


def _terminates(x: Fraction) -> bool:
    return (x * 10**4).denominator == 1


def slips(p: Problem) -> list[Fraction]:
    """Common slips for this kind of problem."""
    x, o, s = p.answer, p.operands, p.subtype
    if s in ("add", "sub"):
        return [x + 10, x - 10]  # a dropped or doubled carry / borrow
    if s == "mul":
        return [x + o[0], x - o[0], x + o[1], x - o[1]]  # one multiple off
    if s == "div":
        return [x + 1, x - 1]
    if s in ("frac_dec", "dec_frac"):
        n, d = x.numerator, x.denominator
        return [Fraction(n + 1, d), Fraction(max(1, n - 1), d), Fraction(d - n, d)]  # neighbour or complement
    if s == "dec_int":
        m, k = o
        return [m * (k + m.denominator), Fraction(m.numerator * k, 10)]  # one step off; 3/8 read as 0.3
    if s == "frac_pm":
        a, op, b = o
        tops = a.numerator + b.numerator if op == "+" else a.numerator - b.numerator
        return [Fraction(tops, a.denominator + b.denominator)] if tops > 0 else []  # adding tops and bottoms
    if s == "mixed":
        a, op, b = o
        first = Fraction(a.numerator, 10)  # the fraction "converted" as 0.n before the subtraction
        return [first + b if op == "+" else abs(first - b), a + b if op == "−" else abs(a - b)]
    if s == "pct_of":
        pc, n = o
        return [Fraction((pc + 1) * n, 100), Fraction((pc - 1) * n, 100)]
    if s == "pct_change":
        start, end = o
        return [Fraction(end - start, end) * 100, -x]  # ÷ the end instead of the start; direction flipped
    if s == "chained":
        return [Fraction(o[0] + o[1])]  # adding the percents, ignoring the cross term
    if s == "reverse":
        pc, after = o
        return [after * (1 - Fraction(pc, 100))]  # taking pc% off the new value instead of dividing
    return []


def near_misses(rng: random.Random, x: Fraction, form: str = "any") -> list[Fraction]:
    """Off by a decimal place, swapped digits, or off by a small amount (a fraction answer: a neighbouring
    numerator, or the denominator halved or doubled)."""
    if form == FRACTION:
        n, d = x.numerator, x.denominator
        return [Fraction(n + 1, d), Fraction(n - 1, d), Fraction(n + 2, d), Fraction(n - 2, d), Fraction(n, 2 * d),
                *([Fraction(n, d // 2)] if d % 2 == 0 else [])]
    out = [x * 10, x / 10]
    text = dec(x)
    spots = [i for i in range(len(text) - 1) if text[i].isdigit() and text[i + 1].isdigit() and text[i] != text[i + 1]]
    if spots:
        i = rng.choice(spots)
        out.append(Fraction(text[:i] + text[i + 1] + text[i] + text[i + 2:]))
    unit = Fraction(1, 10 ** places(x))
    out += [x + unit, x - unit, x + 2 * unit, x - 2 * unit, x + 1, x - 1]
    return out


def distractors(rng: random.Random, p: Problem) -> list[Fraction]:
    """Three wrong options: a common slip first when there is one, then near-misses."""
    x = p.answer
    slip = slips(p)
    rng.shuffle(slip)
    near = near_misses(rng, x, p.form)
    rng.shuffle(near)
    picked: list[Fraction] = []
    shown = {show(p, x)}
    for c in slip[:1] + near + slip[1:]:
        ok = c != x and _terminates(c) and (c > 0 or (p.subtype in SIGNED and c != 0))
        ok = ok and not (p.form == FRACTION and c.denominator == 1)  # no "1/1" among fractions
        if ok and show(p, c) not in shown:
            picked.append(c)
            shown.add(show(p, c))
        if len(picked) == OPTIONS - 1:
            return picked
    raise ValueError(f"not enough distractors for {p.text}")


def question(rng: random.Random, p: Problem) -> Question:
    wrong = distractors(rng, p)
    values = [p.answer, *wrong]
    order = list(range(OPTIONS))
    rng.shuffle(order)
    options = tuple(show(p, values[i]) for i in order)
    return Question(p, options, order.index(0))


def optiver_questions(seed: int | str, n: int = QUESTIONS) -> list[Question]:
    """`n` questions from the seed: families from shuffled bags of (decfrac, pct, core), MEDIUM or HARD each."""
    rng = random.Random(seed)
    out: list[Question] = []
    bag: list[str] = []
    while len(out) < n:
        if not bag:
            bag = list(FAMILY_CYCLE)
            rng.shuffle(bag)
        p = make(rng, bag.pop(), rng.choice((MEDIUM, HARD)))
        out.append(question(rng, p))
    return out
