"""Estimate (arcade): 15 questions, 15 seconds each. Type a number, Enter; points for how close and how fast.
Pure Python, exact arithmetic (Decimal for the answers, Fraction for the scoring), no Textual.

off = |guess − exact| / |exact|. Within 1% → 100 (FULL), 5% → 50 (HALF), 10% → 25 (QUARTER), else 0 (MISS);
bands are inclusive. ×2 if answered within 4s, ×1.5 within 8s, else ×1. A timeout scores 0. No combo.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, ROUND_UP, Decimal, localcontext
from fractions import Fraction
from typing import Any

from met_games.games.math.config import ESTIMATE, MathConfig
from met_games.games.math.problems import EASY, HARD, MEDIUM, size

QUESTIONS = 15
QUESTION_MS = 15_000
MUL, DIV, PCT_OF, SQRT, SMALL = "mul", "div", "pct", "sqrt", "small"
KINDS = (MUL, DIV, PCT_OF, SQRT, SMALL)  # three of each per run
KIND_LABELS = {MUL: "big ×", DIV: "÷ decimal", PCT_OF: "% of", SQRT: "√", SMALL: "× 0.0xxx"}
FULL, HALF, QUARTER, MISS = "full", "half", "quarter", "miss"
BANDS = ((Fraction(1, 100), FULL, 100), (Fraction(5, 100), HALF, 50), (Fraction(10, 100), QUARTER, 25))
SPEEDS = ((4_000, Fraction(2)), (8_000, Fraction(3, 2)))
EIGHT_DP = Decimal("1e-8")
FAMILY = "est"  # its history lines; kept out of the skill tracks
MAX_TYPED = 14
MAX_DRAWS = 10_000
_NUMBER = re.compile(r"(\d+\.?\d*|\.\d+)\Z")


@dataclass(frozen=True)
class Question:
    kind: str
    text: str
    exact: Decimal  # exact; ÷ and √ to 8 dp
    a: Decimal
    b: Decimal  # (√: unused)


def _dec(n: int, dp: int) -> Decimal:
    """n × 10^−dp, exactly."""
    return Decimal(n).scaleb(-dp)


def _num(rng: random.Random, lo: int, hi: int, dp: int) -> Decimal:
    """lo…hi scaled down by dp places, never ending in 0 (so it shows all its digits)."""
    while True:
        n = rng.randint(lo, hi)
        if n % 10:
            return _dec(n, dp)


def is_round(x: Decimal) -> bool:
    """Fewer than three significant digits: 4500, 0.25, 30."""
    return size(Fraction(x)) < 100


def _exact(kind: str, a: Decimal, b: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        if kind == SQRT:
            return a.sqrt().quantize(EIGHT_DP, rounding=ROUND_HALF_EVEN)
        if kind == DIV:
            return (a / b).quantize(EIGHT_DP, rounding=ROUND_HALF_EVEN)
        if kind == PCT_OF:
            return a * b / 100
        return a * b


def _operands(rng: random.Random, kind: str, level: str) -> tuple[Decimal, Decimal]:
    """(a, b) for a kind at a difficulty. EASY 3-digit and 2-digit whole numbers; MEDIUM 4 significant digits with
    1 decimal place; HARD 4–5 significant digits with 2–3 places (√: up to 5 digits)."""
    if kind == SQRT:
        lo, hi = {EASY: (100, 999), MEDIUM: (1000, 9999), HARD: (10000, 99999)}[level]
        while True:
            n = rng.randint(lo, hi)
            if Decimal(n).sqrt() % 1:  # a non-square
                return Decimal(n), Decimal(0)
    if kind == SMALL:  # a 4-digit number (in the difficulty's style) × 0.0xxx
        a = {EASY: lambda: _num(rng, 1000, 9999, 0), MEDIUM: lambda: _num(rng, 1000, 9999, 1),
             HARD: lambda: _num(rng, 1000, 99999, rng.choice((2, 3)))}[level]()
        return a, _num(rng, 101, 999, 4)
    if level == EASY:
        a = _num(rng, 100, 999, 0)
        b = {MUL: lambda: _num(rng, 10, 99, 0), DIV: lambda: _num(rng, 11, 99, 1),
             PCT_OF: lambda: _num(rng, 11, 99, 0)}[kind]()
        return a, b
    if level == MEDIUM:
        a = _num(rng, 1000, 9999, 1)
        b = {MUL: lambda: _num(rng, 100, 999, 1), DIV: lambda: _num(rng, 11, 999, 1),
             PCT_OF: lambda: _num(rng, 101, 999, 1)}[kind]()
        return a, b
    a = _num(rng, 1000, 99999, rng.choice((2, 3)))
    b = {MUL: lambda: _num(rng, 100, 9999, 2), DIV: lambda: _num(rng, 1001, 9999, rng.choice((2, 3))),
         PCT_OF: lambda: _num(rng, 101, 9999, 2)}[kind]()
    return a, b


def text_of(kind: str, a: Decimal, b: Decimal) -> str:
    if kind == SQRT:
        return f"√{a}"
    if kind == PCT_OF:
        return f"{b}% of {a}"
    return f"{a} {'÷' if kind == DIV else '×'} {b}"


def make_question(rng: random.Random, kind: str, level: str) -> Question:
    """A question whose exact answer is at least 1 and not a round number."""
    for _ in range(MAX_DRAWS):
        a, b = _operands(rng, kind, level)
        exact = _exact(kind, a, b)
        if exact >= 1 and not is_round(exact):
            return Question(kind, text_of(kind, a, b), exact, a, b)
    raise RuntimeError(f"no {kind} question at {level}")


def make_questions(seed: int | str, level: str) -> list[Question]:
    """Three of each kind, shuffled."""
    rng = random.Random(seed)
    kinds = [k for k in KINDS for _ in range(QUESTIONS // len(KINDS))]
    rng.shuffle(kinds)
    return [make_question(rng, k, level) for k in kinds]


# ── scoring ─────────────────────────────────────────────────────────────────


def parse_guess(text: str) -> Fraction | None:
    """A typed estimate: digits with an optional decimal point; commas are ignored."""
    text = text.replace(",", "")
    return Fraction(text) if _NUMBER.match(text) else None


def off_by(guess: Fraction, exact: Decimal) -> Fraction:
    e = Fraction(exact)
    return abs(guess - e) / abs(e)


def band(off: Fraction) -> tuple[str, int]:
    for limit, name, pts in BANDS:
        if off <= limit:
            return name, pts
    return MISS, 0


def speed(ms: int) -> Fraction:
    for limit, mult in SPEEDS:
        if ms <= limit:
            return mult
    return Fraction(1)


@dataclass(frozen=True)
class Answered:
    question: Question
    guess: Fraction | None  # None: timed out
    typed: str
    ms: int
    off: Fraction | None
    band: str
    speed: Fraction
    points: Fraction  # band × speed (a half point is possible: 25 × 1.5)

    @property
    def outcome(self) -> str:
        return "timeout" if self.guess is None else self.band


def score(question: Question, typed: str, ms: int) -> Answered:
    guess = parse_guess(typed)
    off = off_by(guess, question.exact)
    name, pts = band(off)
    mult = speed(ms)
    return Answered(question, guess, typed, ms, off, name, mult, pts * mult)


class EstimateRun:
    """15 questions, 15 seconds each; it ends after the 15th."""

    def __init__(self, config: MathConfig, seed: int | str) -> None:
        config.validate()
        self.mode, self.board, self.seed, self.config = ESTIMATE, config.board, seed, config
        self.questions = make_questions(seed, config.difficulty)
        self.scored = True
        self.ladder = None
        self.day = None
        self.ended_early = False
        self.rows: list[Answered] = []
        self.now = 0
        self.shown_at = 0
        self.typed = ""
        self.over = False

    @property
    def question(self) -> Question | None:
        i = len(self.rows)
        return self.questions[i] if i < len(self.questions) else None

    @property
    def time_left_ms(self) -> int:
        return max(0, QUESTION_MS - (self.now - self.shown_at))

    def advance_to(self, ms: int) -> None:
        """Time passes; every question whose 15 seconds ran out scores 0 and the next one starts."""
        if self.over or ms <= self.now:
            return
        while not self.over and ms - self.shown_at >= QUESTION_MS:
            self.now = self.shown_at + QUESTION_MS
            self._record(Answered(self.question, None, self.typed, QUESTION_MS, None, MISS, Fraction(1), Fraction(0)))
        self.now = max(self.now, ms) if not self.over else self.now

    def end(self) -> None:
        self.over = True

    def type(self, ch: str) -> None:
        if not self.over and (ch.isdigit() or ch in ".,") and len(self.typed) < MAX_TYPED:
            self.typed += ch

    def backspace(self) -> None:
        if not self.over:
            self.typed = self.typed[:-1]

    def submit(self) -> Answered | None:
        """Enter: score what's typed (nothing, or not a number: nothing happens)."""
        if self.over or parse_guess(self.typed) is None:
            return None
        return self._record(score(self.question, self.typed, self.now - self.shown_at))

    def _record(self, row: Answered) -> Answered:
        self.rows.append(row)
        self.typed, self.shown_at = "", self.now
        if len(self.rows) >= len(self.questions):
            self.end()
        return row

    # ── score ───────────────────────────────────────────────────────────────

    def count(self, name: str) -> int:
        return sum(r.band == name for r in self.rows)

    @property
    def points(self) -> Fraction:
        return sum((r.points for r in self.rows), Fraction(0))

    @property
    def correct(self) -> int:  # within 10%
        return sum(r.band != MISS for r in self.rows)

    @property
    def skipped(self) -> int:  # timed out
        return sum(r.guess is None for r in self.rows)

    @property
    def wrong(self) -> int:  # answered, but more than 10% off
        return sum(r.guess is not None and r.band == MISS for r in self.rows)

    @property
    def best_combo(self) -> Fraction:
        return Fraction(1)

    def summary(self) -> dict[str, Any]:
        return {name: self.count(name) for name in (FULL, HALF, QUARTER, MISS)}

    def log_rows(self) -> list[dict[str, Any]]:
        return [{"level": self.board, "family": FAMILY, "subtype": f"est_{r.question.kind}", "outcome": r.outcome,
                 "ms": r.ms} for r in self.rows]


# ── display ─────────────────────────────────────────────────────────────────


def two_dp(x: Decimal) -> str:
    return f"{x.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN):,}"


def percent_text(off: Fraction | None) -> str:
    """Rounded up to 0.1%, so a miss just over 10% never reads "10.0%"."""
    if off is None:
        return "—"
    with localcontext() as ctx:
        ctx.prec = 40
        pct = (Decimal(off.numerator) * 100 / Decimal(off.denominator)).quantize(Decimal("0.1"), rounding=ROUND_UP)
    return f"{pct}%"


def points_text(x: Fraction) -> str:
    return f"{x.numerator:,}" if x.denominator == 1 else f"{Decimal(x.numerator) / Decimal(x.denominator):,}"


def speed_text(x: Fraction) -> str:
    return {Fraction(2): "×2", Fraction(3, 2): "×1.5"}.get(x, "×1")
