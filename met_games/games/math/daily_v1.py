"""FROZEN daily generator, v1. A self-contained copy of the Mental Math problem generator as it was at release,
used only by the daily challenge so later engine changes can't change past or future dailies.

DO NOT EDIT. It never imports the main generator (met_games.games.math.problems). To change the daily, add a
daily_v2.py and bump the version on the card; tests/test_math_daily.py pins this one's output.
"""

from __future__ import annotations

import random
from collections import namedtuple
from datetime import date
from fractions import Fraction
from math import gcd

VERSION = "v1"
DAILY_PROBLEMS = 200

EASY, MEDIUM, HARD = "easy", "medium", "hard"
LEVELS = (EASY, MEDIUM, HARD)
CORE, DECFRAC, PCT, DESK = "core", "decfrac", "pct", "desk"
FAMILIES = (CORE, DECFRAC, PCT, DESK)
FAMILY_LABELS = {CORE: "core", DECFRAC: "frac", PCT: "%", DESK: "desk"}
BASE = {CORE: 100, DECFRAC: 150, PCT: 150, DESK: 200}
MAX_PLACES = {CORE: 0, DECFRAC: 4, PCT: 2, DESK: 2}  # every answer terminates within these decimal places

SUBTYPES: dict[str, dict[str, tuple[str, ...]]] = {
    CORE: {EASY: ("add", "sub", "mul", "div"), MEDIUM: ("add", "sub", "mul", "div"),
           HARD: ("add", "sub", "mul", "div")},
    DECFRAC: {EASY: ("frac_dec", "dec_frac", "dec_int"), MEDIUM: ("frac_dec", "dec_frac", "dec_int", "frac_pm"),
              HARD: ("frac_dec", "dec_frac", "dec_int", "mixed")},
    PCT: {EASY: ("pct_of",), MEDIUM: ("pct_of", "pct_change"), HARD: ("chained", "reverse")},
    DESK: {EASY: ("pnl",), MEDIUM: ("pnl", "spread", "notional"), HARD: ("pnl", "vwap")},
}
SUBTYPE_FAMILY = {s: f for f, levels in SUBTYPES.items() for subs in levels.values() for s in subs}
SUBTYPE_LABELS = {
    "add": "addition", "sub": "subtraction", "mul": "multiplication", "div": "division",
    "frac_dec": "fraction → decimal", "dec_frac": "decimal → fraction", "dec_int": "decimal × integer",
    "frac_pm": "fraction ± fraction", "mixed": "fraction ± decimal",
    "pct_of": "percent of", "pct_change": "% change", "chained": "chained %", "reverse": "reverse %",
    "pnl": "P&L", "vwap": "VWAP", "spread": "spread cost", "notional": "notional",
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


# A problem as plain data: the daily screen turns these into the app's own Problem objects.
Problem = namedtuple("Problem", "text answer family subtype level tip_key operands form", defaults=((), "any"))


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
            return Problem(f"{a} + {b}", Fraction(a + b), CORE, "add", level, "add", (a, b))
        while a == b:
            b = rng.randint(lo, hi)
        a, b = max(a, b), min(a, b)
        return Problem(f"{a} − {b}", Fraction(a - b), CORE, "sub", level, "sub", (a, b))
    if subtype == "mul":
        if level == EASY:
            a, b = rng.randint(2, 12), rng.randint(2, 12)
        elif level == MEDIUM:
            a, b = (rng.randint(10, 99), rng.randint(10, 99)) if rng.random() < 0.5 else \
                (rng.randint(100, 999), rng.randint(2, 9))
        else:
            a, b = rng.randint(100, 999), rng.randint(10, 99)
        return Problem(f"{a} × {b}", Fraction(a * b), CORE, "mul", level, mul_tip(a, b), (a, b))
    if level == EASY:
        b, q = rng.randint(2, 12), rng.randint(2, 12)
    elif level == MEDIUM:
        b = rng.randint(2, 9)
        q = rng.randint(-(-100 // b), 999 // b)
    else:
        b = rng.randint(10, 99)
        q = rng.randint(max(2, -(-100 // b)), 99)
    return Problem(f"{b * q} ÷ {b}", Fraction(q), CORE, "div", level, "div", (b * q, b))


# ── decimals & fractions ────────────────────────────────────────────────────

DENOMS = {EASY: (2, 4, 5), MEDIUM: (8,), HARD: (16,)}
PM_DENOMS = (2, 4, 5, 8, 10, 16)  # fraction ± fraction (MEDIUM): ≤ 16 and terminating
DEC_INT = {EASY: (1, 1, (8, 100)), MEDIUM: (8, 8, (16, 96)), HARD: (16, 4, (16, 120))}  # den, k step, k range


def frac_dec_tip(d: int) -> str:
    return {8: "eighths", 16: "sixteenths", 5: "fifths"}.get(d, "quarters")


def decfrac(rng: random.Random, level: str, subtype: str) -> Problem:
    if subtype in ("frac_dec", "dec_frac"):
        d = rng.choice(DENOMS[level])
        x = Fraction(_coprime(rng, d), d)
        if subtype == "frac_dec":
            return Problem(f"{frac(x)} as a decimal", x, DECFRAC, subtype, level, frac_dec_tip(d), (x,), DECIMAL)
        return Problem(f"{dec(x)} as a fraction", x, DECFRAC, subtype, level, "dec_frac", (x,), FRACTION)
    if subtype == "dec_int":
        if level == EASY:
            m = rng.choice((Fraction(1, 2), Fraction(1, 4)))
            k = m.denominator * rng.randint(-(-8 // m.denominator), 100 // m.denominator)
        else:
            d, step, (lo, hi) = DEC_INT[level]
            m = Fraction(_coprime(rng, d), d)
            k = step * rng.randint(-(-lo // step), hi // step)
        return Problem(f"{dec(m)} × {k}", m * k, DECFRAC, subtype, level, "dec_int", (m, k))
    if subtype == "frac_pm":
        while True:
            d1, d2 = rng.choice(PM_DENOMS), rng.choice(PM_DENOMS)
            a, b = Fraction(_coprime(rng, d1), d1), Fraction(_coprime(rng, d2), d2)
            if a != b:
                break
        if rng.random() < 0.5:
            return Problem(f"{frac(a)} + {frac(b)}", a + b, DECFRAC, subtype, level, "frac_pm", (a, "+", b))
        a, b = max(a, b), min(a, b)
        return Problem(f"{frac(a)} − {frac(b)}", a - b, DECFRAC, subtype, level, "frac_pm", (a, "−", b))
    # mixed (HARD): a fraction in eighths or sixteenths and a decimal in sixteenths
    while True:
        d = rng.choice((8, 16))
        a, b = Fraction(_coprime(rng, d), d), Fraction(_coprime(rng, 16), 16)
        if a != b:
            break
    if rng.random() < 0.5:
        return Problem(f"{frac(a)} + {dec(b)}", a + b, DECFRAC, subtype, level, "mixed", (a, "+", b))
    if a > b:
        return Problem(f"{frac(a)} − {dec(b)}", a - b, DECFRAC, subtype, level, "mixed", (a, "−", b))
    return Problem(f"{dec(b)} − {frac(a)}", b - a, DECFRAC, subtype, level, "mixed", (b, "−", a))


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
        return Problem(f"{p}% of {n}", Fraction(p * n, 100), PCT, subtype, level, tip, (p, n))
    if subtype == "pct_change":
        while True:
            s = rng.randint(20, 500)
            c = rng.choice([*range(-50, 0), *range(1, 101)])
            if s * c % 100 == 0:
                break
        e = s + s * c // 100
        return Problem(f"{s} → {e}: % change", Fraction(c), PCT, subtype, level, "pct_change", (s, e))
    if subtype == "chained":
        x = rng.randint(5, 50)
        y = x if rng.random() < 0.25 else rng.randint(5, 50)
        net = Fraction((100 + x) * (100 - y), 100) - 100
        if rng.random() < 0.5:
            text, ops = f"up {x}% then down {y}%: net %", (x, -y)
        else:
            text, ops = f"down {y}% then up {x}%: net %", (-y, x)
        return Problem(text, net, PCT, subtype, level, "chained_same" if x == y else "chained", ops)
    p = rng.choice([q for q in range(-50, 55, 5) if q])
    o = rng.randint(20, 2000)
    after = Fraction(o * (100 + p), 100)
    sign = "+" if p > 0 else "−"
    return Problem(f"after {sign}{abs(p)}% it's {dec(after)}: original", Fraction(o), PCT, subtype, level, "reverse",
                   (p, after))


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


def desk(rng: random.Random, level: str, subtype: str) -> Problem:
    if subtype == "pnl" and level == EASY:
        q = _qty(rng, 1, 5)
        b, s = rng.sample(range(10, 100), 2)
        fills = ((q, Fraction(b)), (-q, Fraction(s)))
        return Problem(f"bought {q} @ {b}, sold {q} @ {s}: P&L", fills_pnl(fills), DESK, "pnl", level, "pnl",
                       (fills, None))
    if subtype == "pnl" and level == MEDIUM:
        q = _qty(rng, 1, 9)
        b = _cents(rng, 1100, 9899)
        s = b + Fraction(rng.choice([*range(-100, 0), *range(1, 101)]), 100)
        fills = ((q, b), (-q, s))
        return Problem(f"bought {q} @ {money(b)}, sold @ {money(s)}: P&L", fills_pnl(fills), DESK, "pnl", level,
                       "pnl", (fills, None))
    if subtype == "spread":
        q = _qty(rng, 1, 10)
        bid = _cents(rng)
        ask = bid + Fraction(rng.randint(1, 10), 100)
        return Problem(f"{money(bid)} / {money(ask)}: buy {q} at the ask, sell at the bid. cost", (ask - bid) * q,
                       DESK, subtype, level, "spread", (bid, ask, q))
    if subtype == "notional":
        q, p = _qty(rng, 1, 9), _cents(rng)
        return Problem(f"notional of {q} @ {money(p)}", q * p, DESK, subtype, level, "notional", (q, p))
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
        listed = ", ".join(f"{q} @ {money(p)}" for q, p in fills)
        return Problem(f"VWAP of {listed}", v, DESK, subtype, level, "vwap", fills)
    # HARD P&L: a buy split into two sells, or a partial sell with the rest marked
    q = _qty(rng, 3, 9)
    b = _cents(rng, 1050, 9949)

    def near() -> Fraction:
        return b + Fraction(rng.choice([*range(-50, 0), *range(1, 51)]), 100)

    if rng.random() < 0.5:
        q1 = _qty(rng, 1, q // 100 - 1)
        s1, s2 = near(), near()
        fills = ((q, b), (-q1, s1), (-(q - q1), s2))
        return Problem(f"bought {q} @ {money(b)}, sold {q1} @ {money(s1)} and {q - q1} @ {money(s2)}: P&L",
                       fills_pnl(fills), DESK, "pnl", level, "pnl_multi", (fills, None))
    q1 = _qty(rng, 1, q // 100 - 1)
    s, m = near(), near()
    fills = ((q, b), (-q1, s))
    return Problem(f"bought {q} @ {money(b)}, sold {q1} @ {money(s)}, mark {money(m)}: P&L", fills_pnl(fills, m),
                   DESK, "pnl", level, "pnl_marked", (fills, m))


MAKERS = {CORE: core, DECFRAC: decfrac, PCT: pct, DESK: desk}


def make(rng: random.Random, family: str, level: str, subtype: str | None = None) -> Problem:
    if subtype is None:
        subtype = rng.choice(SUBTYPES[family][level])
    return MAKERS[family](rng, level, subtype)


def seed_for(day: date) -> str:
    return f"met-math-daily-{day.isoformat()}"


def problems(day: date, n: int = DAILY_PROBLEMS) -> list[Problem]:
    """The day's problems: MEDIUM, all four families from shuffled bags, seeded by the Detroit date."""
    rng = random.Random(seed_for(day))
    out: list[Problem] = []
    bag: list[str] = []
    while len(out) < n:
        if not bag:
            bag = list(FAMILIES)
            rng.shuffle(bag)
        family = bag.pop()
        out.append(make(rng, family, MEDIUM))
    return out
