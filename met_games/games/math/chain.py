"""Chain (arcade): one running number. Each link applies one operation to the carry and your answer becomes the new
carry. Typed and submitted with Enter; a wrong answer or the step clock running out ends the chain. Pure Python,
exact integers, no Textual. The UI feeds time in with `advance_to(ms)`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from met_games.games.math.config import CHAIN, CUSTOM, DIVIDE, PERCENT, PM, TIMES, MathConfig
from met_games.games.math.ladder import ADDSUB, DIV, MUL, PCT_TRACK
from met_games.games.math.problems import CORE, EASY, HARD, MEDIUM, PCT, Problem, mul_tip
from met_games.games.math.run import combo, points

BASE, PCT_BASE = 100, 150
MAX_TYPED = 6
MAX_ROLLS = 1_000
WRONG, TIMEOUT = "wrong", "timeout"
OP_KIND = {"+": PM, "−": PM, "×": TIMES, "÷": DIVIDE, "+%": PERCENT, "−%": PERCENT}
OP_TRACK = {"+": ADDSUB, "−": ADDSUB, "×": MUL, "÷": DIV, "+%": PCT_TRACK, "−%": PCT_TRACK}
OP_SUBTYPE = {"+": "chain_add", "−": "chain_sub", "×": "chain_mul", "÷": "chain_div", "+%": "chain_pct",
              "−%": "chain_pct"}


@dataclass(frozen=True)
class ChainRules:
    max_carry: int  # the carry stays 1 … this
    step_ms: int
    add_max: int  # ± 1 … this
    mul_max: int  # × 2 … this (0: off)
    div_max: int  # exact ÷ 2 … this (0: off)
    percents: tuple[int, ...]  # ± these % when the result is a whole number (empty: off)
    start: tuple[int, int]  # the start number's range
    hide: bool  # HARD: the carry hides after your first answer

    @property
    def kinds(self) -> tuple[str, ...]:
        on = {PM: True, TIMES: self.mul_max > 0, DIVIDE: self.div_max > 0, PERCENT: bool(self.percents)}
        return tuple(k for k, v in on.items() if v)


RULES = {
    EASY: ChainRules(999, 15_000, 99, 9, 9, (), (10, 99), False),
    MEDIUM: ChainRules(9_999, 12_000, 99, 12, 12, (10, 20, 25, 50), (10, 999), False),
    HARD: ChainRules(9_999, 10_000, 99, 19, 19, tuple(range(1, 100)), (10, 999), True),
}


def rules_for(config: MathConfig) -> ChainRules:
    """EASY / MEDIUM / HARD; Custom is MEDIUM with your step clock and operations (± always on)."""
    if config.difficulty != CUSTOM:
        return RULES[config.difficulty]
    base = RULES[MEDIUM]
    ops = set(config.ops)
    return replace(base, step_ms=(config.step_s or base.step_ms // 1000) * 1000,
                   mul_max=base.mul_max if TIMES in ops else 0, div_max=base.div_max if DIVIDE in ops else 0,
                   percents=base.percents if PERCENT in ops else ())


@dataclass(frozen=True)
class Link:
    carry: int  # before this link
    op: str  # + − × ÷ +% −%
    operand: int

    @property
    def answer(self) -> int:
        return apply(self.carry, self.op, self.operand)  # type: ignore[return-value]

    @property
    def kind(self) -> str:
        return OP_KIND[self.op]

    @property
    def track(self) -> str:
        return OP_TRACK[self.op]

    @property
    def base(self) -> int:
        return PCT_BASE if self.kind == PERCENT else BASE

    @property
    def op_text(self) -> str:
        return f"{self.op[0]} {self.operand}%" if self.kind == PERCENT else f"{self.op} {self.operand}"

    @property
    def text(self) -> str:
        return f"{self.carry} {self.op_text}"

    def problem(self) -> Problem:
        """The link as a Problem, for its tip (a % link: the p% of carry part)."""
        c, n = self.carry, self.operand
        if self.kind == PERCENT:
            return Problem(f"{n}% of {c}", Fraction(c * n, 100), PCT, "pct_of", "chain",
                           "pct_10" if n in (10, 25, 50) else "pct_of", (n, c))
        sub, tip = {"+": ("add", "add"), "−": ("sub", "sub"), "×": ("mul", mul_tip(c, n)), "÷": ("div", "div")}[self.op]
        return Problem(self.text, Fraction(self.answer), CORE, sub, "chain", tip, (c, n))


def apply(carry: int, op: str, n: int) -> int | None:
    """The exact result, or None when it isn't a whole number."""
    if op == "+":
        return carry + n
    if op == "−":
        return carry - n
    if op == "×":
        return carry * n
    if op == "÷":
        return carry // n if carry % n == 0 else None
    scaled = carry * (100 + n if op == "+%" else 100 - n)
    return scaled // 100 if scaled % 100 == 0 else None


def valid(carry: int, op: str, n: int, rules: ChainRules) -> bool:
    result = apply(carry, op, n)
    return result is not None and 1 <= result <= rules.max_carry


def roll(rng: random.Random, kind: str, rules: ChainRules) -> tuple[str, int]:
    if kind == PM:
        return rng.choice("+−"), rng.randint(1, rules.add_max)
    if kind == TIMES:
        return "×", rng.randint(2, rules.mul_max)
    if kind == DIVIDE:
        return "÷", rng.randint(2, rules.div_max)
    return rng.choice(("+%", "−%")), rng.choice(rules.percents)


def all_valid(carry: int, rules: ChainRules) -> list[tuple[str, int]]:
    out = [(op, n) for op in "+−" for n in range(1, rules.add_max + 1)]
    out += [("×", n) for n in range(2, rules.mul_max + 1)] + [("÷", n) for n in range(2, rules.div_max + 1)]
    out += [(op, p) for op in ("+%", "−%") for p in rules.percents]
    return [(op, n) for op, n in out if valid(carry, op, n, rules)]


def next_link(rng: random.Random, carry: int, rules: ChainRules) -> Link:
    """A random operation that keeps the carry a whole number within the limit: re-rolled until it does, never
    clamped (after 1,000 rolls, a uniform pick among every valid one — ± always has one)."""
    for _ in range(MAX_ROLLS):
        op, n = roll(rng, rng.choice(rules.kinds), rules)
        if valid(carry, op, n, rules):
            return Link(carry, op, n)
    return Link(carry, *rng.choice(all_valid(carry, rules)))


@dataclass(frozen=True)
class Done:
    link: Link
    given: str  # what you typed ("" on a timeout)
    ms: int
    points: int  # 0 for the link that broke the chain
    outcome: str  # correct | wrong | timeout


class ChainRun:
    """A chain: links until one is wrong or out of time."""

    def __init__(self, config: MathConfig, seed: int | str) -> None:
        config.validate()
        self.mode, self.board, self.seed, self.config = CHAIN, config.board, seed, config
        self.rules = rules_for(config)
        self.rng = random.Random(seed)
        self.scored = True
        self.ladder = None
        self.day = None
        self.ended_early = False
        self.start = self.rng.randint(*self.rules.start)
        self.links: list[Done] = []  # completed links
        self.broke: Done | None = None
        self.link = next_link(self.rng, self.start, self.rules)
        self.now = 0
        self.shown_at = 0
        self.typed = ""
        self.over = False

    # ── clock ───────────────────────────────────────────────────────────────

    @property
    def time_left_ms(self) -> int:
        return max(0, self.rules.step_ms - (self.now - self.shown_at))

    def advance_to(self, ms: int) -> None:
        if self.over or ms <= self.now:
            return
        self.now = ms
        if self.time_left_ms == 0:
            self._break(TIMEOUT)

    def end(self) -> None:
        """Stopped (Ctrl+E / quit) or broken: the link on screen isn't scored."""
        self.over = True

    # ── input ───────────────────────────────────────────────────────────────

    def type(self, ch: str) -> None:
        if not self.over and ch.isdigit() and len(self.typed) < MAX_TYPED:
            self.typed += ch

    def backspace(self) -> None:
        if not self.over:
            self.typed = self.typed[:-1]

    def submit(self) -> Done | None:
        """Enter: check the typed answer (nothing typed: nothing happens)."""
        if self.over or not self.typed:
            return None
        if int(self.typed) != self.link.answer:
            return self._break(WRONG)
        link = self.link
        done = Done(link, self.typed, self.now - self.shown_at, points(link.base, len(self.links)), "correct")
        self.links.append(done)
        self.link = next_link(self.rng, link.answer, self.rules)
        self.typed, self.shown_at = "", self.now
        return done

    def _break(self, why: str) -> Done:
        self.broke = Done(self.link, self.typed if why == WRONG else "", self.now - self.shown_at, 0, why)
        self.end()
        return self.broke

    # ── view ────────────────────────────────────────────────────────────────

    @property
    def carry(self) -> int:
        return self.link.carry

    @property
    def hidden(self) -> bool:
        """HARD: after your first answer the carry and the chain log hide."""
        return self.rules.hide and bool(self.links)

    @property
    def shown(self) -> str:
        return f"? {self.link.op_text}" if self.hidden else self.link.text

    # ── score ───────────────────────────────────────────────────────────────

    @property
    def length(self) -> int:
        return len(self.links)

    @property
    def points(self) -> int:
        return sum(d.points for d in self.links)

    @property
    def combo(self) -> Fraction:
        return combo(len(self.links))

    @property
    def best_combo(self) -> Fraction:
        return combo(len(self.links) - 1) if self.links else Fraction(1)

    @property
    def avg_ms(self) -> Fraction | None:
        return Fraction(sum(d.ms for d in self.links), len(self.links)) if self.links else None

    # the fields every run summary carries
    @property
    def correct(self) -> int:
        return self.length

    @property
    def skipped(self) -> int:
        return int(self.broke is not None and self.broke.outcome == TIMEOUT)

    @property
    def wrong(self) -> int:
        return int(self.broke is not None and self.broke.outcome == WRONG)

    def summary(self) -> dict[str, Any]:
        return {"length": self.length, "start": self.start,
                "broke": self.broke.outcome if self.broke else ("ended" if self.ended_early else None)}

    def log_rows(self) -> list[dict[str, Any]]:
        """One history line per link answered (the breaking one included)."""
        done = self.links + ([self.broke] if self.broke else [])
        return [{"level": self.board, "family": PCT if d.link.kind == PERCENT else CORE,
                 "subtype": OP_SUBTYPE[d.link.op], "track": d.link.track, "outcome": d.outcome, "ms": d.ms}
                for d in done]
