"""Mental Math problem engine: four families of problems with exact answers, the Zetamac standard
generator, and answer parsing. Pure Python, exact arithmetic (Fraction), no Textual.

Every problem carries its display text, its exact answer, a family (core | decfrac | pct | desk), a subtype,
the difficulty it was drawn at, a tip key, its operands (so tips and tests can rebuild it), and its solution steps.
Each difficulty's core spec is the ceiling for every step (`within_difficulty`); `make` redraws any problem over it.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from fractions import Fraction
from math import gcd, lcm
from typing import Any

EASY, MEDIUM, HARD = "easy", "medium", "hard"
LEVELS = (EASY, MEDIUM, HARD)
CORE, DECFRAC, PCT, DESK = "core", "decfrac", "pct", "desk"
FAMILIES = (CORE, DECFRAC, PCT, DESK)
FAMILY_LABELS = {CORE: "core", DECFRAC: "frac", PCT: "%", DESK: "desk"}
BASE = {CORE: 100, DECFRAC: 150, PCT: 150, DESK: 200}
# Probability (prob.py) is a family of its own, only in the Probability drill: never in FAMILIES, so it is never mixed
# into Sprint, Survival, Chain or the daily.
PROB = "prob"
FAMILY_LABELS[PROB] = "prob"
BASE[PROB] = 200
MAX_PLACES = {CORE: 0, DECFRAC: 4, PCT: 2, DESK: 2}  # every answer terminates within these decimal places

SUBTYPES: dict[str, dict[str, tuple[str, ...]]] = {
    CORE: {EASY: ("add", "sub", "mul", "div"), MEDIUM: ("add", "sub", "mul", "div"),
           HARD: ("add", "sub", "mul", "div")},
    DECFRAC: {EASY: ("frac_dec", "dec_frac", "dec_int"), MEDIUM: ("frac_dec", "dec_frac", "dec_int", "frac_pm"),
              HARD: ("frac_dec", "dec_frac", "dec_int", "mixed")},
    PCT: {EASY: ("pct_of",), MEDIUM: ("pct_of", "pct_change"), HARD: ("chained", "reverse")},
    DESK: {EASY: ("pnl", "spread", "notional"), MEDIUM: ("pnl", "spread", "notional", "vwap"), HARD: ("pnl", "vwap")},
}
SUBTYPE_FAMILY = {s: f for f, levels in SUBTYPES.items() for subs in levels.values() for s in subs}
SUBTYPE_LABELS = {
    "add": "addition", "sub": "subtraction", "mul": "multiplication", "div": "division",
    "frac_dec": "fraction → decimal", "dec_frac": "decimal → fraction", "dec_int": "decimal × integer",
    "frac_pm": "fraction ± fraction", "mixed": "fraction ± decimal",
    "pct_of": "percent of", "pct_change": "% change", "chained": "chained %", "reverse": "reverse %",
    "pnl": "P&L", "vwap": "VWAP", "spread": "crossing the spread", "notional": "notional",
}

ANY, DECIMAL, FRACTION = "any", "decimal", "fraction"  # the form an answer must be typed in


# ── formatting ──────────────────────────────────────────────────────────────


def places(x: Fraction) -> int:
    """Decimal places needed to write x exactly (x must terminate within 8 places)."""
    for k in range(9):
        if (x * 10**k).denominator == 1:
            return k
    raise ValueError(f"{x} does not terminate")


def dec(x: Fraction | int, min_places: int = 0) -> str:
    """x as an exact decimal string: 0.375, 42.10 (with min_places=2), -1.5."""
    x = Fraction(x)
    k = max(places(x), min_places)
    n = abs(x * 10**k).numerator
    digits = str(n).rjust(k + 1, "0")
    body = f"{digits[:-k]}.{digits[-k:]}" if k else digits
    return f"-{body}" if x < 0 else body


def money(x: Fraction) -> str:
    """A price with exactly two decimals: 42.10."""
    return dec(x, 2)


def frac(x: Fraction) -> str:
    return f"{x.numerator}/{x.denominator}"


# ── problems ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Problem:
    text: str
    answer: Fraction
    family: str
    subtype: str
    level: str  # easy | medium | hard | zetamac
    tip_key: str
    operands: tuple[Any, ...] = ()
    form: str = ANY  # frac→dec wants a decimal, dec→frac a fraction; everything else takes either
    steps: tuple[tuple[str, Any, Any], ...] = ()  # the solution, (op, a, b) each; the last one gives the answer

    @property
    def base(self) -> int:
        return BASE[self.family]

    @property
    def answer_text(self) -> str:
        return frac(self.answer) if self.form == FRACTION else dec(self.answer)


# ── the difficulty ceiling ──────────────────────────────────────────────────
# A step is (op, a, b): add | sub | mul | div, or frac (write a/b as a fraction — no arithmetic). Each difficulty's
# core spec caps every step: ± EASY 2 digits · MEDIUM 3 · HARD 4; × EASY up to 12×12 · MEDIUM 2×2 or 3×1 · HARD 3×2;
# a ÷ b = q counts as the multiplication q × b. Decimal points and trailing zeros don't count toward size
# (0.25 × 300 is 25 × 3), and × or ÷ by a power of ten is a shift, not a step.

ADD_DIGITS = {EASY: 2, MEDIUM: 3, HARD: 4}


def size(x: Fraction | int) -> int:
    """|x| without its decimal point and trailing zeros: 0.25 → 25, 300 → 3, 42.10 → 421."""
    x = abs(Fraction(x))
    n = (x * 10 ** places(x)).numerator
    while n and n % 10 == 0:
        n //= 10
    return n


def add_width(a: Fraction | int, b: Fraction | int) -> int:
    """Digit columns that a + b really works on. Aligned and without shared trailing zeros: a shorter number only
    touches its own columns (the carry or borrow into the rest is an increment); a subtraction of equal-length numbers
    skips their shared leading digits (42.62 − 42.37 is 62 − 37)."""
    a, b = Fraction(a), Fraction(b)
    k = max(places(a), places(b))
    big, small = sorted((int(abs(a) * 10**k), int(abs(b) * 10**k)), reverse=True)
    while small and big % 10 == 0 and small % 10 == 0:
        big, small = big // 10, small // 10
    if small == 0:
        return 0
    sb, ss = str(big), str(small)
    if len(ss) < len(sb):
        return len(ss)
    if (a < 0) != (b < 0):  # a subtraction of magnitudes
        i = 0
        while i < len(sb) - 1 and sb[i] == ss[i]:
            i += 1
        return len(sb) - i
    return len(sb)


def mul_ok(a: Fraction | int, b: Fraction | int, level: str) -> bool:
    hi, lo = sorted((size(a), size(b)), reverse=True)
    if lo <= 1:  # × 1, × 10, × 0.01 …: a shift
        return True
    dh, dl = len(str(hi)), len(str(lo))
    if level == EASY:
        return hi <= 12
    if level == MEDIUM:
        return dh <= 2 or (dh <= 3 and dl <= 1)
    return dh <= 3 and dl <= 2


def step_result(op: str, a: Any, b: Any) -> Fraction:
    a, b = Fraction(a), Fraction(b)
    return {"add": a + b, "sub": a - b, "mul": a * b, "div": a / b, "frac": a / b}[op]


def step_ok(step: tuple[str, Any, Any], level: str) -> bool:
    op, a, b = step
    try:
        if op == "frac":
            return True
        if op in ("add", "sub"):
            return add_width(a, b if op == "add" else -Fraction(b)) <= ADD_DIGITS[level]
        if op == "mul":
            return mul_ok(a, b, level)
        if op == "div":
            return mul_ok(Fraction(a) / Fraction(b), b, level)
    except ValueError:  # a non-terminating decimal: never a mental step
        return False
    return False


def within_difficulty(steps: Any, level: str) -> bool:
    """True if every solution step is within the level's core spec (any other level, e.g. zetamac, has none)."""
    return level not in LEVELS or all(step_ok(s, level) for s in steps)


def _coprime(rng: random.Random, d: int) -> int:
    return rng.choice([n for n in range(1, d) if gcd(n, d) == 1])


# ── core ────────────────────────────────────────────────────────────────────

ADD_RANGE = {EASY: (10, 99), MEDIUM: (100, 999), HARD: (1000, 9999)}


def mul_tip(a: int, b: int) -> str:
    for n, key in ((25, "mul_25"), (11, "mul_11"), (5, "mul_5"), (9, "mul_9")):
        if n in (a, b):
            return key
    return "mul_split"


def core(rng: random.Random, level: str, subtype: str) -> Problem:
    if subtype in ("add", "sub"):
        lo, hi = ADD_RANGE[level]
        a, b = rng.randint(lo, hi), rng.randint(lo, hi)
        if subtype == "add":
            return Problem(f"{a} + {b}", Fraction(a + b), CORE, "add", level, "add", (a, b), steps=(("add", a, b),))
        while a == b:
            b = rng.randint(lo, hi)
        a, b = max(a, b), min(a, b)
        return Problem(f"{a} − {b}", Fraction(a - b), CORE, "sub", level, "sub", (a, b), steps=(("sub", a, b),))
    if subtype == "mul":
        if level == EASY:
            a, b = rng.randint(2, 12), rng.randint(2, 12)
        elif level == MEDIUM:
            a, b = (rng.randint(10, 99), rng.randint(10, 99)) if rng.random() < 0.5 else \
                (rng.randint(100, 999), rng.randint(2, 9))
        else:
            a, b = rng.randint(100, 999), rng.randint(10, 99)
        return Problem(f"{a} × {b}", Fraction(a * b), CORE, "mul", level, mul_tip(a, b), (a, b),
                       steps=(("mul", a, b),))
    if level == EASY:
        b, q = rng.randint(2, 12), rng.randint(2, 12)
    elif level == MEDIUM:
        b = rng.randint(2, 9)
        q = rng.randint(-(-100 // b), 999 // b)
    else:
        b = rng.randint(10, 99)
        q = rng.randint(max(2, -(-100 // b)), 99)
    return Problem(f"{b * q} ÷ {b}", Fraction(q), CORE, "div", level, "div", (b * q, b), steps=(("div", b * q, b),))


# ── decimals & fractions ────────────────────────────────────────────────────

DENOMS = {EASY: (2, 4, 5), MEDIUM: (8,), HARD: (16,)}
PM_DENOMS = (2, 4, 5, 8, 10, 16)  # fraction ± fraction (MEDIUM): ≤ 16 and terminating
DEC_INT = {EASY: (1, 1, (8, 100)), MEDIUM: (8, 8, (16, 96)), HARD: (16, 4, (16, 120))}  # den, k step, k range


def frac_dec_tip(d: int) -> str:
    return {8: "eighths", 16: "sixteenths", 5: "fifths"}.get(d, "quarters")


def decfrac(rng: random.Random, level: str, subtype: str) -> Problem:
    if subtype in ("frac_dec", "dec_frac"):
        d = rng.choice(DENOMS[level])
        n = _coprime(rng, d)
        x, unit = Fraction(n, d), Fraction(1, d)  # n/d = n × (1/d): 3/8 = 3 × 0.125
        if subtype == "frac_dec":
            return Problem(f"{frac(x)} as a decimal", x, DECFRAC, subtype, level, frac_dec_tip(d), (x,), DECIMAL,
                           (("mul", n, unit),))
        return Problem(f"{dec(x)} as a fraction", x, DECFRAC, subtype, level, "dec_frac", (x,), FRACTION,
                       (("div", x, unit), ("frac", n, d)))
    if subtype == "dec_int":
        if level == EASY:
            m = rng.choice((Fraction(1, 2), Fraction(1, 4)))
            k = m.denominator * rng.randint(-(-8 // m.denominator), 100 // m.denominator)
        else:
            d, step, (lo, hi) = DEC_INT[level]
            m = Fraction(_coprime(rng, d), d)
            k = step * rng.randint(-(-lo // step), hi // step)
        d = m.denominator  # (n/d) × k = n × (k ÷ d)
        return Problem(f"{dec(m)} × {k}", m * k, DECFRAC, subtype, level, "dec_int", (m, k),
                       steps=(("div", k, d), ("mul", m.numerator, Fraction(k, d))))
    if subtype == "frac_pm":
        while True:
            d1, d2 = rng.choice(PM_DENOMS), rng.choice(PM_DENOMS)
            a, b = Fraction(_coprime(rng, d1), d1), Fraction(_coprime(rng, d2), d2)
            if a != b:
                break
        plus = rng.random() < 0.5
        if not plus:
            a, b = max(a, b), min(a, b)
        # over the common denominator L: a = a1/L, b = b1/L
        big = lcm(a.denominator, b.denominator)
        fa, fb = big // a.denominator, big // b.denominator
        a1, b1 = a.numerator * fa, b.numerator * fb
        steps = (("div", big, a.denominator), ("mul", a.numerator, fa), ("div", big, b.denominator),
                 ("mul", b.numerator, fb), ("add" if plus else "sub", a1, b1), ("frac", a1 + b1 if plus else a1 - b1,
                                                                               big))
        sign = "+" if plus else "−"
        return Problem(f"{frac(a)} {sign} {frac(b)}", a + b if plus else a - b, DECFRAC, subtype, level, "frac_pm",
                       (a, sign, b), steps=steps)
    # mixed (HARD): a fraction in eighths or sixteenths and a decimal in sixteenths, worked in sixteenths
    while True:
        d = rng.choice((8, 16))
        a, b = Fraction(_coprime(rng, d), d), Fraction(_coprime(rng, 16), 16)
        if a != b:
            break
    sixteenth = Fraction(1, 16)
    an, bn = a.numerator * (16 // d), b.numerator
    head = (("div", b, sixteenth), ("div", 16, d), ("mul", a.numerator, 16 // d))
    if rng.random() < 0.5:
        return Problem(f"{frac(a)} + {dec(b)}", a + b, DECFRAC, subtype, level, "mixed", (a, "+", b),
                       steps=(*head, ("add", an, bn), ("frac", an + bn, 16)))
    if a > b:
        return Problem(f"{frac(a)} − {dec(b)}", a - b, DECFRAC, subtype, level, "mixed", (a, "−", b),
                       steps=(*head, ("sub", an, bn), ("frac", an - bn, 16)))
    return Problem(f"{dec(b)} − {frac(a)}", b - a, DECFRAC, subtype, level, "mixed", (b, "−", a),
                   steps=(*head, ("sub", bn, an), ("frac", bn - an, 16)))


# ── percentages ─────────────────────────────────────────────────────────────


def pct(rng: random.Random, level: str, subtype: str) -> Problem:
    if subtype == "pct_of":
        if level == EASY:
            p, n = rng.choice((10, 25, 50)), 20 * rng.randint(2, 50)
        else:
            while True:
                p, n = rng.randint(1, 99), rng.randint(20, 990)
                if p * n % 10 == 0:  # answer has at most one decimal place
                    break
        tip = "pct_10" if p in (10, 25, 50) else "pct_of"
        # 10% / 25% / 50% is ÷ 10 / 4 / 2; any other p% is p × n, then ÷ 100
        steps = (("div", n, 100 // p),) if p in (10, 25, 50) else (("mul", p, n), ("div", p * n, 100))
        return Problem(f"{p}% of {n}", Fraction(p * n, 100), PCT, subtype, level, tip, (p, n), steps=steps)
    if subtype == "pct_change":
        while True:
            s = rng.randint(20, 500)
            c = rng.choice([*range(-50, 0), *range(1, 101)])
            if s * c % 100 == 0:
                break
        e = s + s * c // 100
        return Problem(f"{s} → {e}: % change", Fraction(c), PCT, subtype, level, "pct_change", (s, e),
                       steps=(("sub", e, s), ("div", e - s, s), ("mul", Fraction(c, 100), 100)))
    if subtype == "chained":
        x = rng.randint(5, 50)
        y = x if rng.random() < 0.25 else rng.randint(5, 50)
        net = Fraction((100 + x) * (100 - y), 100) - 100  # = x − y − xy/100
        if rng.random() < 0.5:
            text, ops = f"up {x}% then down {y}%: net %", (x, -y)
        else:
            text, ops = f"down {y}% then up {x}%: net %", (-y, x)
        steps = (("mul", x, y), ("div", x * y, 100), ("sub", x, y), ("sub", x - y, Fraction(x * y, 100)))
        return Problem(text, net, PCT, subtype, level, "chained_same" if x == y else "chained", ops, steps=steps)
    p = rng.choice([q for q in range(-50, 55, 5) if q])
    o = rng.randint(20, 2000)
    after = Fraction(o * (100 + p), 100)
    sign = "+" if p > 0 else "−"
    return Problem(f"after {sign}{abs(p)}% it's {dec(after)}: original", Fraction(o), PCT, subtype, level, "reverse",
                   (p, after), steps=(("add", 100, p), ("div", 100 + p, 100), ("div", after, Fraction(100 + p, 100))))


# ── desk ────────────────────────────────────────────────────────────────────


def _qty(rng: random.Random, lo: int, hi: int) -> int:
    return 100 * rng.randint(lo, hi)


def _cents(rng: random.Random, lo: int = 1000, hi: int = 9999) -> Fraction:
    return Fraction(rng.randint(lo, hi), 100)


def fills_pnl(fills: tuple[tuple[int, Fraction], ...], mark: Fraction | None = None) -> Fraction:
    """P&L of signed fills (+qty bought, −qty sold), any open position marked at `mark`."""
    cash = -sum(q * p for q, p in fills)
    pos = sum(q for q, _ in fills)
    return cash + (pos * mark if pos else 0)


def vwap(fills: tuple[tuple[int, Fraction], ...]) -> Fraction:
    return sum(q * p for q, p in fills) / sum(q for q, _ in fills)


def _diff(rng: random.Random, level: str) -> Fraction:
    """A price difference: EASY $1–9, MEDIUM a multiple of 0.05 up to 0.95."""
    return Fraction(rng.randint(1, 9)) if level == EASY else Fraction(5 * rng.randint(1, 19), 100)


def _price(rng: random.Random, level: str, room: Fraction = Fraction(0)) -> Fraction:
    """EASY whole dollars 10–99, else cents 10.00–99.99, leaving `room` below 100 for a difference on top."""
    if level == EASY:
        return Fraction(rng.randint(10, 99 - int(room)))
    return _cents(rng, 1000, 9999 - int(room * 100))


def _px(x: Fraction, level: str) -> str:
    return dec(x) if level == EASY else money(x)


def _round_trip(rng: random.Random, level: str) -> Problem:
    """EASY / MEDIUM P&L: one buy, one sell of the same size; P&L = (sell − buy) × size."""
    q = _qty(rng, 1, 9)
    d = _diff(rng, level)
    b = _price(rng, level, d)
    s = b + d
    if rng.random() < 0.5 and b - d >= 10:
        s = b - d
    fills = ((q, b), (-q, s))
    return Problem(f"bought {q} @ {_px(b, level)}, sold {q} @ {_px(s, level)} · P&L = ?", fills_pnl(fills), DESK, "pnl",
                   level, "pnl", (fills, None), steps=(("sub", s, b), ("mul", s - b, q)))


def _vwap_two(rng: random.Random, level: str) -> Problem:
    """MEDIUM VWAP: two fills of equal size (VWAP = the midpoint) or in a 2:1 ratio (a third of the way)."""
    ratio = rng.choice(("equal", "low2", "high2"))
    d = Fraction(10 * rng.randint(1, 9), 100) if ratio == "equal" else Fraction(15 * rng.randint(1, 6), 100)
    lo = _price(rng, level, d)
    hi = lo + d
    if ratio == "equal":
        q_lo = q_hi = _qty(rng, 1, 9)
        mid = (("div", d, 2),)
    else:
        small = _qty(rng, 1, 4)
        q_lo, q_hi = (2 * small, small) if ratio == "low2" else (small, 2 * small)
        mid = (("div", d, 3),) if ratio == "low2" else (("div", d, 3), ("mul", d / 3, 2))
    fills = ((q_lo, lo), (q_hi, hi))
    v = vwap(fills)
    listed = ", ".join(f"{q} @ {money(p)}" for q, p in fills)
    return Problem(f"fills {listed} · VWAP = ?", v, DESK, "vwap", level, "vwap", fills,
                   steps=(("sub", hi, lo), *mid, ("add", lo, v - lo)))


def desk(rng: random.Random, level: str, subtype: str) -> Problem:
    if subtype == "pnl" and level in (EASY, MEDIUM):
        return _round_trip(rng, level)
    if subtype == "spread":
        q = _qty(rng, 1, 9)
        width = _diff(rng, level)
        bid = _price(rng, level, width)
        ask = bid + width
        # buying at the ask and selling at the bid loses the spread: P&L = (bid − ask) × q, always negative
        return Problem(f"bid {_px(bid, level)} / ask {_px(ask, level)} · buy {q} at the ask, sell at the bid · P&L = ?",
                       -width * q, DESK, subtype, level, "spread", (bid, ask, q),
                       steps=(("sub", bid, ask), ("mul", bid - ask, q)))
    if subtype == "notional":
        q = _qty(rng, 1, 9)
        # EASY: a whole-dollar price that's 1 digit and zeros (1–9 or 10–90); MEDIUM: three digits (42.10)
        p = Fraction(rng.randint(1, 9) * rng.choice((1, 10))) if level == EASY else Fraction(rng.randint(100, 999), 10)
        return Problem(f"buy {q} @ {_px(p, level)} · notional = ?", q * p, DESK, subtype, level, "notional", (q, p),
                       steps=(("mul", q, p),))
    if subtype == "vwap" and level == MEDIUM:
        return _vwap_two(rng, level)
    if subtype == "vwap":
        while True:
            base = rng.randint(1000, 9900)
            n = rng.choice((2, 3))
            prices = sorted(Fraction(c, 100) for c in rng.sample(range(base, base + 51), n))
            qtys = [_qty(rng, 1, 5) for _ in range(n)]
            fills = tuple(zip(qtys, prices))
            v = vwap(fills)
            if (v * 100).denominator == 1:  # VWAP within 2 dp
                break
        # offsets from the lowest price, weighted: VWAP = low + Σ q·(p − low) / Σ q
        low = prices[0]
        steps: list[tuple[str, Any, Any]] = []
        weighted = []
        for q, px in fills[1:]:
            steps += [("sub", px, low), ("mul", q, px - low)]
            weighted.append(q * (px - low))
        if len(weighted) == 2:
            steps.append(("add", *weighted))
        steps.append(("add", qtys[0], qtys[1]))
        if n == 3:
            steps.append(("add", qtys[0] + qtys[1], qtys[2]))
        steps += [("div", sum(weighted), sum(qtys)), ("add", low, v - low)]
        listed = ", ".join(f"{q} @ {money(p)}" for q, p in fills)
        return Problem(f"fills {listed} · VWAP = ?", v, DESK, subtype, level, "vwap", fills, steps=tuple(steps))
    # HARD P&L: a buy split into two sells, or a partial sell with the rest marked
    q = _qty(rng, 3, 9)
    b = _cents(rng, 1050, 9949)

    def near() -> Fraction:
        return b + Fraction(rng.choice([*range(-50, 0), *range(1, 51)]), 100)

    def legs(p1: Fraction, q1: int, p2: Fraction, q2: int) -> tuple[tuple[str, Any, Any], ...]:
        return (("sub", p1, b), ("mul", p1 - b, q1), ("sub", p2, b), ("mul", p2 - b, q2),
                ("add", (p1 - b) * q1, (p2 - b) * q2))

    q1 = _qty(rng, 1, q // 100 - 1)
    if rng.random() < 0.5:
        s1, s2 = near(), near()
        fills = ((q, b), (-q1, s1), (-(q - q1), s2))
        return Problem(f"bought {q} @ {money(b)}, sold {q1} @ {money(s1)} and {q - q1} @ {money(s2)} · P&L = ?",
                       fills_pnl(fills), DESK, "pnl", level, "pnl_multi", (fills, None),
                       steps=legs(s1, q1, s2, q - q1))
    s, m = near(), near()
    fills = ((q, b), (-q1, s))
    return Problem(f"bought {q} @ {money(b)}, sold {q1} @ {money(s)}, rest marked @ {money(m)} · P&L = ?",
                   fills_pnl(fills, m),
                   DESK, "pnl", level, "pnl_marked", (fills, m), steps=legs(s, q1, m, q - q1))


MAKERS = {CORE: core, DECFRAC: decfrac, PCT: pct, DESK: desk}
MAX_DRAWS = 10_000


def make(rng: random.Random, family: str, level: str, subtype: str | None = None) -> Problem:
    """A problem of `family` at `level` (a random subtype unless given), redrawn until every step is within the
    level's ceiling."""
    if subtype is None:
        subtype = rng.choice(SUBTYPES[family][level])
    for _ in range(MAX_DRAWS):
        problem = MAKERS[family](rng, level, subtype)
        if within_difficulty(problem.steps, level):
            return problem
    raise RuntimeError(f"no {family}/{subtype} problem fits {level}")


class ProblemStream:
    """Problems for a run, from the seed only. Families come out of shuffled bags (each enabled family `weight`
    times per bag), so they appear evenly; the subtype is uniform within the family's difficulty. `pool`, a list of
    (family, subtype) or (family, subtype, difficulty), restricts the stream to those subtypes (the drill)."""

    def __init__(self, seed: int | str, families: tuple[str, ...] = FAMILIES,
                 levels: dict[str, str] | None = None, weights: dict[str, int] | None = None,
                 pool: list[tuple[str, str]] | None = None, level: str = MEDIUM) -> None:
        self.rng = random.Random(seed)
        self.levels = {f: (levels or {}).get(f, level) for f in FAMILIES}
        self.pool = list(pool) if pool else None
        weights = weights or {}
        self.entries: list[Any] = self.pool or [f for f in families for _ in range(max(1, weights.get(f, 1)))]
        if not self.entries:
            raise ValueError("pick at least one family")
        self.bag: list[Any] = []

    def next(self) -> Problem:
        if not self.bag:
            self.bag = list(self.entries)
            self.rng.shuffle(self.bag)
        entry = self.bag.pop()
        if self.pool:
            family, subtype, *level = entry
            return make(self.rng, family, level[0] if level else self.levels[family], subtype)
        return make(self.rng, entry, self.levels[entry])


# ── Zetamac standard ────────────────────────────────────────────────────────

ZETAMAC = "zetamac"


def zetamac(rng: random.Random) -> Problem:
    """The arithmetic.zetamac.com default: (2–100) + (2–100), subtraction as reversed addition, (2–12) × (2–100),
    division as reversed multiplication."""
    op = rng.choice(("add", "sub", "mul", "div"))
    if op in ("add", "sub"):
        a, b = rng.randint(2, 100), rng.randint(2, 100)
        if op == "add":
            return Problem(f"{a} + {b}", Fraction(a + b), CORE, "add", ZETAMAC, "add", (a, b))
        return Problem(f"{a + b} − {a}", Fraction(b), CORE, "sub", ZETAMAC, "sub", (a + b, a))
    a, b = rng.randint(2, 12), rng.randint(2, 100)
    if op == "mul":
        return Problem(f"{a} × {b}", Fraction(a * b), CORE, "mul", ZETAMAC, mul_tip(a, b), (a, b))
    return Problem(f"{a * b} ÷ {a}", Fraction(b), CORE, "div", ZETAMAC, "div", (a * b, a))


class ZetamacStream:
    def __init__(self, seed: int | str) -> None:
        self.rng = random.Random(seed)

    def next(self) -> Problem:
        return zetamac(self.rng)


# ── answers ─────────────────────────────────────────────────────────────────

ALLOWED = set("0123456789.-/")
_DECIMAL = re.compile(r"-?(\d+\.?\d*|\.\d+)\Z")
_FRACTION = re.compile(r"-?\d+/\d+\Z")


def parse_answer(text: str) -> Fraction | None:
    """The exact value of typed text — a decimal (".5", "-1.25", "3.") or a fraction ("13/16") — else None."""
    if not (_DECIMAL.match(text) or _FRACTION.match(text)):
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def accepts(problem: Problem, text: str) -> bool:
    """True the moment `text` is exactly the answer, in a form the problem takes."""
    value = parse_answer(text)
    if value is None or value != problem.answer:
        return False
    if problem.form == DECIMAL and "/" in text:
        return False
    if problem.form == FRACTION and "/" not in text:
        return False
    return True
