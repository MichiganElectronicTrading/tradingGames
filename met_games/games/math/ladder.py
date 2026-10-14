"""Adaptive ladders: seven skill tracks, ten levels each. Pure Python, exact arithmetic, no Textual.

Every subtype belongs to exactly one track (`SUBTYPE_TRACK`). L3, L6 and L9 are today's EASY, MEDIUM and HARD
generators (the very same draws); L1–2 are easier than EASY, L10 harder than HARD, and the rungs in between
interpolate operand sizes and digit counts. A rung below L10 is also held to the next anchor's step ceiling
(`within_difficulty`), so L4 never needs more than MEDIUM's mental steps.
"""

from __future__ import annotations

import random
import re
from dataclasses import replace
from fractions import Fraction
from math import lcm
from typing import Any

from met_games.games.math.problems import (
    CORE,
    DECFRAC,
    DESK,
    EASY,
    FRACTION,
    HARD,
    MAX_DRAWS,
    MAX_PLACES,
    MEDIUM,
    PCT,
    PROB,
    SUBTYPES,
    DECIMAL,
    Problem,
    _coprime,
    dec,
    fills_pnl,
    frac,
    frac_dec_tip,
    make,
    money,
    mul_tip,
    places,
    size,
    vwap,
    within_difficulty,
)

ADDSUB, MUL, DIV, DEC, FRAC, PCT_TRACK, DESK_TRACK = "addsub", "mul", "div", "dec", "frac", "pct", "desk"
TRACKS = (ADDSUB, MUL, DIV, DEC, FRAC, PCT_TRACK, DESK_TRACK)  # the Sprint / Survival tracks
PROB_TRACK = "prob"  # the Probability drill's own track (prob.py has its ladder)
ALL_TRACKS = (*TRACKS, PROB_TRACK)
TRACK_LABELS = {ADDSUB: "+/−", MUL: "×", DIV: "÷", DEC: "dec", FRAC: "frac", PCT_TRACK: "%", DESK_TRACK: "desk",
                PROB_TRACK: "prob"}

# The one place subtypes meet tracks. Decimals & fractions split by what you start from: a decimal (dec → frac,
# dec × int) is `dec`; a fraction (frac → dec, frac ± frac, frac ± dec) is `frac`.
SUBTYPE_TRACK = {
    "add": ADDSUB, "sub": ADDSUB, "mul": MUL, "div": DIV,
    "dec_frac": DEC, "dec_int": DEC, "frac_dec": FRAC, "frac_pm": FRAC, "mixed": FRAC,
    "pct_of": PCT_TRACK, "pct_change": PCT_TRACK, "chained": PCT_TRACK, "reverse": PCT_TRACK,
    "pnl": DESK_TRACK, "spread": DESK_TRACK, "notional": DESK_TRACK, "vwap": DESK_TRACK,
}
TRACK_FAMILY = {ADDSUB: CORE, MUL: CORE, DIV: CORE, DEC: DECFRAC, FRAC: DECFRAC, PCT_TRACK: PCT, DESK_TRACK: DESK,
                PROB_TRACK: PROB}
FAMILY_TRACKS = {f: tuple(t for t in TRACKS if TRACK_FAMILY[t] == f) for f in (CORE, DECFRAC, PCT, DESK)}

LEVEL_MIN, LEVEL_MAX = 1, 10
ANCHORS = {3: EASY, 6: MEDIUM, 9: HARD}
ANCHOR_LEVEL = {v: k for k, v in ANCHORS.items()}
CEILING = {1: EASY, 2: EASY, 4: MEDIUM, 5: MEDIUM, 7: HARD, 8: HARD}  # L10: none

# The most significant digits any number in a rung's problem text can have (0.375 → 3, 300 → 1, 42.15 → 4).
# Non-decreasing up every ladder; the anchors are what today's EASY / MEDIUM / HARD generators reach.
DIGITS = {
    ADDSUB: (1, 2, 2, 3, 3, 3, 4, 4, 4, 5),
    MUL: (1, 1, 2, 2, 3, 3, 3, 3, 3, 4),
    DIV: (2, 2, 3, 3, 3, 3, 4, 4, 4, 5),
    DEC: (2, 2, 2, 3, 3, 3, 4, 4, 4, 4),
    FRAC: (1, 1, 1, 1, 1, 2, 3, 4, 4, 4),
    PCT_TRACK: (2, 2, 2, 2, 3, 3, 4, 5, 5, 6),
    DESK_TRACK: (2, 2, 2, 4, 4, 4, 4, 4, 4, 4),
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def level_name(level: int) -> str:
    return f"L{level}"


def anchor_of(level: str) -> str:
    """The nearest of EASY / MEDIUM / HARD for a problem's level ("L5" → medium); anything else is unchanged."""
    if not level.startswith("L"):
        return level
    n = int(level[1:])
    return EASY if n <= 4 else MEDIUM if n <= 7 else HARD


def digits(problem: Problem) -> int:
    """The most significant digits of any number in the problem text."""
    return max((len(str(size(Fraction(m)))) for m in _NUMBER.findall(problem.text)), default=0)


# ── the rungs ───────────────────────────────────────────────────────────────
# Each non-anchor rung: {subtype: params}; the subtype is drawn uniformly from its keys.

R = tuple[int, int]
RUNGS: dict[str, dict[int, dict[str, Any]]] = {
    ADDSUB: {
        1: {"add": ((2, 9), (2, 9)), "sub": ((2, 9), (2, 9))},
        2: {"add": ((10, 99), (2, 9)), "sub": ((10, 99), (2, 9))},
        4: {"add": ((100, 999), (10, 99)), "sub": ((100, 999), (10, 99))},
        5: {"add": ((100, 999), (100, 499)), "sub": ((100, 999), (100, 499))},
        7: {"add": ((1000, 9999), (100, 999)), "sub": ((1000, 9999), (100, 999))},
        8: {"add": ((1000, 9999), (1000, 4999)), "sub": ((1000, 9999), (1000, 4999))},
        10: {"add": ((10000, 99999), (10000, 99999)), "sub": ((10000, 99999), (10000, 99999))},
    },
    MUL: {  # shapes: (a range, b range), one drawn uniformly
        1: {"mul": [((2, 9), (2, 5))]},
        2: {"mul": [((2, 9), (2, 9))]},
        4: {"mul": [((10, 99), (2, 9))]},
        5: {"mul": [((10, 99), (10, 19)), ((100, 999), (2, 5))]},
        7: {"mul": [((100, 999), (10, 19)), ((10, 99), (10, 99))]},
        8: {"mul": [((100, 999), (10, 49))]},
        10: {"mul": [((1000, 9999), (10, 99)), ((100, 999), (100, 999))]},
    },
    DIV: {  # shapes: (divisor range, quotient range)
        1: {"div": [((2, 5), (2, 9))]},
        2: {"div": [((2, 9), (2, 9))]},
        4: {"div": [((2, 9), (10, 50))]},
        5: {"div": [((2, 9), (10, 99))]},
        7: {"div": [((10, 19), (10, 99))]},
        8: {"div": [((10, 49), (10, 99))]},
        10: {"div": [((10, 99), (100, 999))]},
    },
    DEC: {  # dec_frac: denominators · dec_int: (denominators, any numerator?, k step ("den" = the denominator), k range)
        1: {"dec_frac": (2, 4), "dec_int": ((2,), False, "den", (2, 40))},
        2: {"dec_frac": (2, 4, 5), "dec_int": ((2, 4), False, "den", (4, 60))},
        4: {"dec_frac": (4, 5, 8), "dec_int": ((4, 5), True, "den", (8, 100))},
        5: {"dec_frac": (8,), "dec_int": ((8,), True, 8, (16, 48))},
        7: {"dec_frac": (8, 16), "dec_int": ((8,), True, 4, (16, 120))},
        8: {"dec_frac": (16,), "dec_int": ((16,), True, 8, (16, 120))},
        10: {"dec_frac": (16, 40, 80), "dec_int": ((16, 40), True, 1, (16, 240))},
    },
    FRAC: {  # frac_dec: denominators · frac_pm: denominators · mixed: (fraction denominators, decimal denominators)
        1: {"frac_dec": (2, 4)},
        2: {"frac_dec": (2, 4, 10)},
        4: {"frac_dec": (4, 5, 8), "frac_pm": (2, 4)},
        5: {"frac_dec": (8,), "frac_pm": (2, 4, 8)},
        7: {"frac_dec": (8, 16), "frac_pm": (4, 8, 16), "mixed": ((4, 8), (8,))},
        8: {"frac_dec": (16,), "mixed": ((8, 16), (8, 16))},
        10: {"frac_dec": (16, 40, 80), "frac_pm": (16, 20, 40, 80), "mixed": ((16, 40), (16,))},
    },
    PCT_TRACK: {
        # pct_of: (percents, (n lo, n hi, n step), answer dp) · pct_change: ((start lo, hi), change step)
        # chained: ((lo, hi), step) · reverse: (percent step, largest |percent|, (original lo, hi))
        1: {"pct_of": ((10, 50), (20, 200, 20), 0)},
        2: {"pct_of": ((10, 25, 50), (20, 500, 20), 0)},
        4: {"pct_of": ((5, 10, 20, 25, 50, 75), (20, 1000, 20), 0)},
        5: {"pct_of": (tuple(range(5, 100, 5)), (20, 990, 10), 1), "pct_change": ((20, 200), 10)},
        7: {"pct_change": ((20, 500), 1), "chained": ((5, 30), 5), "reverse": (10, 50, (20, 500))},
        8: {"chained": ((5, 40), 1), "reverse": (5, 50, (20, 1000))},
        10: {"chained": ((5, 75), 1), "reverse": (5, 75, (100, 5000))},
    },
    DESK_TRACK: {
        # trip / spread: (largest qty in hundreds, "whole" | "cents" prices, price differences)
        # notional: (largest qty in hundreds, price kind) · vwap: ("two", ratios) | ("many", fills, width in cents)
        # pnl "split": (qty range in hundreds, kinds, offset step in cents, largest offset in cents)
        1: {"spread": (5, "whole", tuple(Fraction(d) for d in range(1, 6))), "notional": (5, "digit")},
        2: {"pnl": ("trip", 9, "whole", tuple(Fraction(d) for d in range(1, 10))),
            "spread": (9, "whole", tuple(Fraction(d) for d in range(1, 10))), "notional": (9, "digit")},
        4: {"pnl": ("trip", 9, "cents", tuple(Fraction(d, 10) for d in range(1, 10))),
            "spread": (9, "cents", tuple(Fraction(d, 10) for d in range(1, 10))), "notional": (9, "halves")},
        5: {"pnl": ("trip", 9, "cents", tuple(Fraction(d, 20) for d in range(1, 20))),
            "spread": (9, "cents", tuple(Fraction(d, 20) for d in range(1, 20))), "notional": (9, "tenths"),
            "vwap": ("two", ("equal",))},
        7: {"pnl": ("split", (3, 6), ("multi",), 5, 50), "vwap": ("two", ("equal", "low2", "high2"))},
        8: {"pnl": ("split", (3, 9), ("multi", "marked"), 5, 50), "vwap": ("many", (2,), 51)},
        10: {"pnl": ("split", (3, 19), ("multi", "marked"), 1, 100), "vwap": ("many", (3, 4), 101)},
    },
}


def track_subtypes(track: str, level: int) -> tuple[str, ...]:
    if level in ANCHORS:
        family = TRACK_FAMILY[track]
        return tuple(s for s in SUBTYPES[family][ANCHORS[level]] if SUBTYPE_TRACK[s] == track)
    return tuple(RUNGS[track][level])


# ── core ────────────────────────────────────────────────────────────────────


def _addsub(rng: random.Random, sub: str, ranges: tuple[R, R]) -> Problem:
    (alo, ahi), (blo, bhi) = ranges
    while True:
        x, y = rng.randint(alo, ahi), rng.randint(blo, bhi)
        if sub == "add" or x != y:
            break
    if sub == "add":
        a, b = (x, y) if rng.random() < 0.5 else (y, x)
        return Problem(f"{a} + {b}", Fraction(a + b), CORE, "add", "", "add", (a, b), steps=(("add", a, b),))
    a, b = max(x, y), min(x, y)
    return Problem(f"{a} − {b}", Fraction(a - b), CORE, "sub", "", "sub", (a, b), steps=(("sub", a, b),))


def _mul(rng: random.Random, _: str, shapes: list[tuple[R, R]]) -> Problem:
    (alo, ahi), (blo, bhi) = rng.choice(shapes)
    a, b = rng.randint(alo, ahi), rng.randint(blo, bhi)
    return Problem(f"{a} × {b}", Fraction(a * b), CORE, "mul", "", mul_tip(a, b), (a, b), steps=(("mul", a, b),))


def _div(rng: random.Random, _: str, shapes: list[tuple[R, R]]) -> Problem:
    (blo, bhi), (qlo, qhi) = rng.choice(shapes)
    b, q = rng.randint(blo, bhi), rng.randint(qlo, qhi)
    return Problem(f"{b * q} ÷ {b}", Fraction(q), CORE, "div", "", "div", (b * q, b), steps=(("div", b * q, b),))


# ── decimals & fractions ────────────────────────────────────────────────────


def _dec_frac(rng: random.Random, denoms: tuple[int, ...]) -> Problem:
    d = rng.choice(denoms)
    n = _coprime(rng, d)
    x = Fraction(n, d)
    return Problem(f"{dec(x)} as a fraction", x, DECFRAC, "dec_frac", "", "dec_frac", (x,), FRACTION,
                   (("div", x, Fraction(1, d)), ("frac", n, d)))


def _frac_dec(rng: random.Random, denoms: tuple[int, ...]) -> Problem:
    d = rng.choice(denoms)
    n = _coprime(rng, d)
    x = Fraction(n, d)
    return Problem(f"{frac(x)} as a decimal", x, DECFRAC, "frac_dec", "", frac_dec_tip(d), (x,), DECIMAL,
                   (("mul", n, Fraction(1, d)),))


def _dec_int(rng: random.Random, params: tuple[Any, ...]) -> Problem:
    dens, any_numerator, step, (lo, hi) = params
    d = rng.choice(dens)
    m = Fraction(_coprime(rng, d) if any_numerator else 1, d)
    step = d if step == "den" else step
    k = step * rng.randint(-(-lo // step), hi // step)
    return Problem(f"{dec(m)} × {k}", m * k, DECFRAC, "dec_int", "", "dec_int", (m, k),
                   steps=(("div", k, d), ("mul", m.numerator, Fraction(k, d))))


def _frac_pm(rng: random.Random, denoms: tuple[int, ...]) -> Problem:
    while True:
        d1, d2 = rng.choice(denoms), rng.choice(denoms)
        a, b = Fraction(_coprime(rng, d1), d1), Fraction(_coprime(rng, d2), d2)
        if a != b:
            break
    plus = rng.random() < 0.5
    if not plus:
        a, b = max(a, b), min(a, b)
    big = lcm(a.denominator, b.denominator)
    fa, fb = big // a.denominator, big // b.denominator
    a1, b1 = a.numerator * fa, b.numerator * fb
    steps = (("div", big, a.denominator), ("mul", a.numerator, fa), ("div", big, b.denominator),
             ("mul", b.numerator, fb), ("add" if plus else "sub", a1, b1), ("frac", a1 + b1 if plus else a1 - b1, big))
    sign = "+" if plus else "−"
    return Problem(f"{frac(a)} {sign} {frac(b)}", a + b if plus else a - b, DECFRAC, "frac_pm", "", "frac_pm",
                   (a, sign, b), steps=steps)


def _mixed(rng: random.Random, params: tuple[tuple[int, ...], tuple[int, ...]]) -> Problem:
    fdens, ddens = params
    while True:
        d1, d2 = rng.choice(fdens), rng.choice(ddens)
        a, b = Fraction(_coprime(rng, d1), d1), Fraction(_coprime(rng, d2), d2)
        if a != b:
            break
    big = lcm(d1, d2)
    an, bn = a.numerator * (big // d1), b.numerator * (big // d2)
    head = (("div", b, Fraction(1, d2)), ("div", big, d1), ("mul", a.numerator, big // d1), ("div", big, d2),
            ("mul", b.numerator, big // d2))
    if rng.random() < 0.5:
        return Problem(f"{frac(a)} + {dec(b)}", a + b, DECFRAC, "mixed", "", "mixed", (a, "+", b),
                       steps=(*head, ("add", an, bn), ("frac", an + bn, big)))
    if a > b:
        return Problem(f"{frac(a)} − {dec(b)}", a - b, DECFRAC, "mixed", "", "mixed", (a, "−", b),
                       steps=(*head, ("sub", an, bn), ("frac", an - bn, big)))
    return Problem(f"{dec(b)} − {frac(a)}", b - a, DECFRAC, "mixed", "", "mixed", (b, "−", a),
                   steps=(*head, ("sub", bn, an), ("frac", bn - an, big)))


def _decfrac(rng: random.Random, sub: str, params: Any) -> Problem:
    return {"dec_frac": _dec_frac, "frac_dec": _frac_dec, "dec_int": _dec_int, "frac_pm": _frac_pm,
            "mixed": _mixed}[sub](rng, params)


# ── percentages ─────────────────────────────────────────────────────────────


def _multiple(rng: random.Random, lo: int, hi: int, step: int) -> int:
    return step * rng.randint(-(-lo // step), hi // step)


def _pct(rng: random.Random, sub: str, params: Any) -> Problem:
    if sub == "pct_of":
        percents, (lo, hi, step), dp = params
        while True:
            p, n = rng.choice(percents), _multiple(rng, lo, hi, step)
            if (Fraction(p * n, 100) * 10**dp).denominator == 1:
                break
        tip = "pct_10" if p in (10, 25, 50) else "pct_of"
        steps = (("div", n, 100 // p),) if p in (10, 25, 50) else (("mul", p, n), ("div", p * n, 100))
        return Problem(f"{p}% of {n}", Fraction(p * n, 100), PCT, sub, "", tip, (p, n), steps=steps)
    if sub == "pct_change":
        (lo, hi), step = params
        changes = [c for c in range(-50, 101, step) if c]
        while True:
            s, c = rng.randint(lo, hi), rng.choice(changes)
            if s * c % 100 == 0:
                break
        e = s + s * c // 100
        return Problem(f"{s} → {e}: % change", Fraction(c), PCT, sub, "", "pct_change", (s, e),
                       steps=(("sub", e, s), ("div", e - s, s), ("mul", Fraction(c, 100), 100)))
    if sub == "chained":
        (lo, hi), step = params
        x = _multiple(rng, lo, hi, step)
        y = x if rng.random() < 0.25 else _multiple(rng, lo, hi, step)
        net = Fraction((100 + x) * (100 - y), 100) - 100
        if rng.random() < 0.5:
            text, ops = f"up {x}% then down {y}%: net %", (x, -y)
        else:
            text, ops = f"down {y}% then up {x}%: net %", (-y, x)
        steps = (("mul", x, y), ("div", x * y, 100), ("sub", x, y), ("sub", x - y, Fraction(x * y, 100)))
        return Problem(text, net, PCT, sub, "", "chained_same" if x == y else "chained", ops, steps=steps)
    step, top, (lo, hi) = params
    p = rng.choice([q for q in range(-top, top + 1, step) if q and q % step == 0])
    o = rng.randint(lo, hi)
    after = Fraction(o * (100 + p), 100)
    sign = "+" if p > 0 else "−"
    return Problem(f"after {sign}{abs(p)}% it's {dec(after)}: original", Fraction(o), PCT, sub, "", "reverse",
                   (p, after), steps=(("add", 100, p), ("div", 100 + p, 100), ("div", after, Fraction(100 + p, 100))))


# ── desk ────────────────────────────────────────────────────────────────────


def _price(rng: random.Random, kind: str, room: Fraction) -> Fraction:
    if kind == "whole":
        return Fraction(rng.randint(10, 99 - int(room)))
    return Fraction(rng.randint(1000, 9999 - int(room * 100)), 100)


def _px(x: Fraction, kind: str) -> str:
    return dec(x) if kind == "whole" else money(x)


def _desk(rng: random.Random, sub: str, params: Any) -> Problem:
    if sub == "spread":
        top, kind, diffs = params
        q = 100 * rng.randint(1, top)
        width = rng.choice(diffs)
        bid = _price(rng, kind, width)
        ask = bid + width
        return Problem(f"{_px(bid, kind)} / {_px(ask, kind)}: buy {q} at the ask, sell at the bid. cost", width * q,
                       DESK, sub, "", "spread", (bid, ask, q), steps=(("sub", ask, bid), ("mul", width, q)))
    if sub == "notional":
        top, kind = params
        q = 100 * rng.randint(1, top)
        p = {"digit": lambda: Fraction(rng.randint(1, 9)),
             "halves": lambda: Fraction(rng.randint(21, 199), 2),
             "tenths": lambda: Fraction(rng.randint(100, 999), 10)}[kind]()
        shown = dec(p) if kind == "digit" else money(p)
        return Problem(f"notional of {q} @ {shown}", q * p, DESK, sub, "", "notional", (q, p), steps=(("mul", q, p),))
    if sub == "vwap":
        return _vwap(rng, params)
    if params[0] == "trip":
        _, top, kind, diffs = params
        q = 100 * rng.randint(1, top)
        d = rng.choice(diffs)
        b = _price(rng, kind, d)
        s = b + d
        if rng.random() < 0.5 and b - d >= 10:
            s = b - d
        fills = ((q, b), (-q, s))
        return Problem(f"bought {q} @ {_px(b, kind)}, sold @ {_px(s, kind)}: P&L", fills_pnl(fills), DESK, "pnl", "",
                       "pnl", (fills, None), steps=(("sub", s, b), ("mul", s - b, q)))
    _, (qlo, qhi), kinds, step, top = params
    q = 100 * rng.randint(qlo, qhi)
    b = Fraction(rng.randint(1000 + top, 9999 - top), 100)
    offsets = [c for c in range(-top, top + 1, step) if c]

    def near() -> Fraction:
        return b + Fraction(rng.choice(offsets), 100)

    def legs(p1: Fraction, q1: int, p2: Fraction, q2: int) -> tuple[tuple[str, Any, Any], ...]:
        return (("sub", p1, b), ("mul", p1 - b, q1), ("sub", p2, b), ("mul", p2 - b, q2),
                ("add", (p1 - b) * q1, (p2 - b) * q2))

    q1 = 100 * rng.randint(1, q // 100 - 1)
    if rng.choice(kinds) == "multi":
        s1, s2 = near(), near()
        fills = ((q, b), (-q1, s1), (-(q - q1), s2))
        return Problem(f"bought {q} @ {money(b)}, sold {q1} @ {money(s1)} and {q - q1} @ {money(s2)}: P&L",
                       fills_pnl(fills), DESK, "pnl", "", "pnl_multi", (fills, None), steps=legs(s1, q1, s2, q - q1))
    s, m = near(), near()
    fills = ((q, b), (-q1, s))
    return Problem(f"bought {q} @ {money(b)}, sold {q1} @ {money(s)}, mark {money(m)}: P&L", fills_pnl(fills, m),
                   DESK, "pnl", "", "pnl_marked", (fills, m), steps=legs(s, q1, m, q - q1))


def _vwap(rng: random.Random, params: tuple[Any, ...]) -> Problem:
    if params[0] == "two":
        ratio = rng.choice(params[1])
        d = Fraction(10 * rng.randint(1, 9), 100) if ratio == "equal" else Fraction(15 * rng.randint(1, 6), 100)
        lo = _price(rng, "cents", d)
        hi = lo + d
        if ratio == "equal":
            q_lo = q_hi = 100 * rng.randint(1, 9)
            mid = (("div", d, 2),)
        else:
            small = 100 * rng.randint(1, 4)
            q_lo, q_hi = (2 * small, small) if ratio == "low2" else (small, 2 * small)
            mid = (("div", d, 3),) if ratio == "low2" else (("div", d, 3), ("mul", d / 3, 2))
        fills = ((q_lo, lo), (q_hi, hi))
        v = vwap(fills)
        listed = ", ".join(f"{q} @ {money(p)}" for q, p in fills)
        return Problem(f"VWAP of {listed}", v, DESK, "vwap", "", "vwap", fills,
                       steps=(("sub", hi, lo), *mid, ("add", lo, v - lo)))
    _, counts, width = params
    while True:
        base = rng.randint(1000, 9999 - width)
        n = rng.choice(counts)
        prices = sorted(Fraction(c, 100) for c in rng.sample(range(base, base + width), n))
        qtys = [100 * rng.randint(1, 5) for _ in range(n)]
        fills = tuple(zip(qtys, prices))
        v = vwap(fills)
        if (v * 100).denominator == 1:
            break
    low = prices[0]
    steps: list[tuple[str, Any, Any]] = []
    weighted = []
    for q, px in fills[1:]:
        steps += [("sub", px, low), ("mul", q, px - low)]
        weighted.append(q * (px - low))
    total_w = weighted[0]
    for w in weighted[1:]:
        steps.append(("add", total_w, w))
        total_w += w
    total_q = qtys[0]
    for q in qtys[1:]:
        steps.append(("add", total_q, q))
        total_q += q
    steps += [("div", total_w, total_q), ("add", low, v - low)]
    listed = ", ".join(f"{q} @ {money(p)}" for q, p in fills)
    return Problem(f"VWAP of {listed}", v, DESK, "vwap", "", "vwap", fills, steps=tuple(steps))


MAKERS = {ADDSUB: _addsub, MUL: _mul, DIV: _div, DEC: _decfrac, FRAC: _decfrac, PCT_TRACK: _pct, DESK_TRACK: _desk}


def well_shaped(problem: Problem) -> bool:
    """The answer-shape rules every problem keeps: positive (or a signed % / P&L), terminating within its family's
    decimal places, and a whole number for core."""
    try:
        return places(problem.answer) <= MAX_PLACES[problem.family]
    except ValueError:
        return False


def make_at(rng: random.Random, track: str, level: int, subtype: str | None = None) -> Problem:
    """A problem on `track` at `level` (1–10). The anchors are today's generators; the level reads "L<n>"."""
    if not LEVEL_MIN <= level <= LEVEL_MAX:
        raise ValueError(f"level must be {LEVEL_MIN}–{LEVEL_MAX}")
    if track == PROB_TRACK:
        from met_games.games.math.prob import make_level

        return make_level(rng, level, subtype)
    subs = track_subtypes(track, level)
    if subtype is None:
        subtype = subs[0] if len(subs) == 1 else rng.choice(subs)
    if level in ANCHORS:
        return replace(make(rng, TRACK_FAMILY[track], ANCHORS[level], subtype), level=level_name(level))
    params = RUNGS[track][level][subtype]
    ceiling = CEILING.get(level)
    for _ in range(MAX_DRAWS):
        p = MAKERS[track](rng, subtype, params)
        if well_shaped(p) and (ceiling is None or within_difficulty(p.steps, ceiling)):
            return replace(p, level=level_name(level))
    raise RuntimeError(f"no {track} L{level} problem fits")
