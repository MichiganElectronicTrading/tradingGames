"""Mental Math shortcut tips: a general rule per tip key, plus a worked example built from a problem's own numbers.
Pure Python, exact arithmetic."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from math import lcm

from met_games.games.math.problems import Problem, dec, frac, money, size


@dataclass(frozen=True)
class Tip:
    key: str
    title: str
    rule: str
    example: Callable[[Problem], str] | None = None


def _lead(n: int) -> tuple[int, int]:
    """Split n into its leading place and the rest: 347 → (300, 47), 63 → (60, 3)."""
    place = 10 ** (len(str(n)) - 1)
    return n - n % place, n % place


def _add(p: Problem) -> str:
    a, b = p.operands
    up = -(-b // 10) * 10
    if up == b:
        return f"{a} + {b} = {a + b}"
    return f"{a} + {b} = {a} + {up} − {up - b} = {a + up} − {up - b} = {a + b}"


def _sub(p: Problem) -> str:
    a, b = p.operands
    step = 100 if b >= 100 else 10
    r = -(-b // step) * step
    if r >= a:
        r = -(-b // 10) * 10
    if r == b or r >= a:
        return f"{b} up to {a}: {a} − {b} = {a - b}"
    return f"{b} → {r} is {r - b}, {r} → {a} is {a - r}: {r - b} + {a - r} = {a - b}"


def _mul_split(p: Problem) -> str:
    a, b = p.operands
    if a < 10 and b < 10:
        return f"{a} × {b} = {a * b}  (a times-table fact: know it cold)"
    x, y = (a, b) if b >= 10 else (b, a)
    lead, rest = _lead(y)
    if rest == 0:
        place = 10 ** (len(str(y)) - 1)
        return f"{x} × {y} = {x} × {y // place} × {place} = {x * (y // place):,} × {place} = {x * y:,}"
    return f"{x} × {y} = {x} × {lead} + {x} × {rest} = {x * lead:,} + {x * rest:,} = {x * y:,}"


def _times(n: int) -> Callable[[Problem], str]:
    def example(p: Problem) -> str:
        a, b = p.operands
        x = b if a == n else a
        if n == 25:
            return f"{x} × 25 = {x} × 100 ÷ 4 = {x * 100:,} ÷ 4 = {x * 25:,}"
        if n == 5:
            return f"{x} × 5 = {x} × 10 ÷ 2 = {x * 10:,} ÷ 2 = {x * 5:,}"
        if n == 11:
            return f"{x} × 11 = {x * 10:,} + {x} = {x * 11:,}"
        return f"{x} × 9 = {x * 10:,} − {x} = {x * 9:,}"
    return example


def _div(p: Problem) -> str:
    n, d = p.operands
    q = n // d
    if q < 10:
        return f"{d} × {q} = {n}, so {n} ÷ {d} = {q}"
    lead, rest = _lead(q)
    return f"{d} × {lead} = {d * lead:,}, {n - d * lead:,} left = {d} × {rest} → {n:,} ÷ {d} = {q}"


def _frac_dec(p: Problem) -> str:
    x = p.answer
    n, d = x.numerator, x.denominator
    unit = Fraction(1, d)
    return f"{frac(x)} = {n} × {dec(unit)} = {dec(x)}"


def _dec_frac(p: Problem) -> str:
    x = p.answer
    k = len(dec(x).split(".")[1])
    return f"{dec(x)} = {x * 10**k}/{10**k} = {frac(x)}"


def _dec_int(p: Problem) -> str:
    m, k = p.operands
    n, d = m.numerator, m.denominator
    if n == 1:
        return f"{dec(m)} × {k} = {k} ÷ {d} = {dec(m * k)}"
    return f"{dec(m)} × {k} = {k} ÷ {d} × {n} = {dec(Fraction(k, d))} × {n} = {dec(m * k)}"


def _common(p: Problem) -> str:
    a, op, b = p.operands
    den = lcm(a.denominator, b.denominator)
    ta, tb = a * den, b * den
    res = p.answer * den
    return (f"{p.text} = {ta}/{den} {op} {tb}/{den} = {res}/{den}"
            + (f" = {frac(p.answer)}" if p.answer.denominator != den else "") + f" = {dec(p.answer)}")


def _pct_10(p: Problem) -> str:
    pc, n = p.operands
    how = {10: f"{n} ÷ 10", 25: f"{n} ÷ 4", 50: f"{n} ÷ 2"}.get(pc, f"{n} × {pc} ÷ 100")
    return f"{pc}% of {n} = {how} = {dec(p.answer)}"


def _pct_of(p: Problem) -> str:
    pc, n = p.operands
    tens, units = pc - pc % 10, pc % 10
    if not tens or not units:
        return f"{pc}% of {n} = {n} × {pc} ÷ 100 = {dec(p.answer)}  (or {n}% of {pc})"
    t, u = Fraction(n * tens, 100), Fraction(n * units, 100)
    return f"{pc}% of {n} = {tens}% ({dec(t)}) + {units}% ({dec(u)}) = {dec(p.answer)}"


def _pct_change(p: Problem) -> str:
    s, e = p.operands
    return f"({e} − {s}) ÷ {s} = {dec(Fraction(e - s, s))} = {dec(p.answer)}%"


def _signed(n: int) -> str:
    return f"+{n}" if n >= 0 else f"−{-n}"


def _chained(p: Problem) -> str:
    x, y = p.operands
    cross = dec(Fraction(abs(x * y), 100))
    return f"{_signed(x)}% then {_signed(y)}%: {_signed(x)} {_signed(y)} − {abs(x)} × {abs(y)} ÷ 100 = " \
           f"{x + y} − {cross} = {dec(p.answer)}%"


def _chained_same(p: Problem) -> str:
    x = abs(p.operands[0])
    return f"up and down {x}%: net −{x}² ÷ 100 = −{dec(Fraction(x * x, 100))}%"


def _reverse(p: Problem) -> str:
    pc, after = p.operands
    factor = 1 + Fraction(pc, 100)
    return f"{dec(after)} ÷ {dec(factor)} = {dec(p.answer)}  (not {dec(after)} {'−' if pc > 0 else '+'} {abs(pc)}%)"


def _pnl(p: Problem) -> str:
    fills, mark = p.operands
    (q, buy), *sells = fills
    parts = [f"{-sq} × ({_px(sp)} − {_px(buy)})" for sq, sp in sells]
    values = [-sq * (sp - buy) for sq, sp in sells]
    pos = q + sum(sq for sq, _ in sells)
    if mark is not None and pos:
        parts.append(f"{pos} × ({_px(mark)} − {_px(buy)})")
        values.append(pos * (mark - buy))
    if len(parts) == 1:
        return f"{parts[0]} = {dec(p.answer)}"
    return f"{' + '.join(parts)} = {' + '.join(dec(v) for v in values)} = {dec(p.answer)}".replace("+ -", "− ")


def _px(x: Fraction) -> str:
    return dec(x) if x.denominator == 1 else money(x)


def _vwap(p: Problem) -> str:
    fills = p.operands
    total = sum(q for q, _ in fills)
    low = fills[0][1]
    parts = [f"{money(px - low)} × {q}/{total}" for q, px in fills[1:]]
    return f"{money(low)} + {' + '.join(parts)} = {money(low)} + {dec(p.answer - low)} = {dec(p.answer)}"


def _spread(p: Problem) -> str:
    bid, ask, q = p.operands
    return f"({_px(ask)} − {_px(bid)}) × {q} = {dec(ask - bid)} × {q} = {dec(p.answer)}"


def _notional(p: Problem) -> str:
    q, px = p.operands
    if px.denominator == 1:  # EASY: one digit and zeros
        return f"{q} × {dec(px)} = {size(q)} × {size(px)} = {size(q) * size(px)}, then the zeros = {dec(p.answer)}"
    whole = px.numerator // px.denominator
    cents = px - whole
    return f"{q} × {money(px)} = {q} × {whole} + {q} × {dec(cents)} = {q * whole:,} + {dec(q * cents)} = {dec(p.answer)}"


TIPS: dict[str, Tip] = {t.key: t for t in (
    Tip("add", "Round and adjust", "Round one number up to the next ten, add, then take back what you added.", _add),
    Tip("sub", "Count up", "Count up from the smaller number: to the next round number, then on to the bigger one.",
        _sub),
    Tip("mul_split", "Split a factor", "Split one factor into its leading part and the rest, multiply each, add.",
        _mul_split),
    Tip("mul_25", "×25", "×25 = ×100 ÷ 4.", _times(25)),
    Tip("mul_5", "×5", "×5 = ×10 ÷ 2.", _times(5)),
    Tip("mul_11", "×11", "×11 = ×10 + the number itself.", _times(11)),
    Tip("mul_9", "×9", "×9 = ×10 − the number itself.", _times(9)),
    Tip("div", "Chunk the dividend", "Take off a big round multiple of the divisor first, then divide what's left.",
        _div),
    Tip("quarters", "Halves and quarters", "1/2 = 0.5, 1/4 = 0.25, 3/4 = 0.75.", _frac_dec),
    Tip("fifths", "Fifths", "1/5 = 0.2, so n fifths = 0.2 × n.", _frac_dec),
    Tip("eighths", "The 1/8 family", "1/8 = 0.125: 3/8 = 0.375, 5/8 = 0.625, 7/8 = 0.875.", _frac_dec),
    Tip("sixteenths", "Sixteenths", "1/16 = 0.0625, half of 1/8: n/16 = n × 0.0625.", _frac_dec),
    Tip("dec_frac", "Over a power of ten", "Write the digits over 10, 100, 1000 … and cancel; know the 1/8 family "
        "by sight.", _dec_frac),
    Tip("dec_int", "Decimal as a fraction", "Turn the decimal into its fraction, then divide first: "
        "0.375 × 48 = 48 ÷ 8 × 3.", _dec_int),
    Tip("frac_pm", "Common denominator", "Put both fractions over the common denominator, then add or subtract "
        "the tops.", _common),
    Tip("mixed", "Convert first", "Convert the decimal to a fraction (sixteenths: 0.0625 each) before you subtract.",
        _common),
    Tip("pct_10", "Easy percents", "10% moves the decimal point one place, 25% is a quarter, 50% a half.", _pct_10),
    Tip("pct_of", "Split the percent", "p% of n = n% of p; or split p into tens and units and add.", _pct_of),
    Tip("pct_change", "% change", "% change = (new − start) ÷ start — always divide by the start.", _pct_change),
    Tip("chained", "Chained percents", "Net % of a then b = a + b + a × b ÷ 100 (a, b signed).", _chained),
    Tip("chained_same", "Up x then down x", "Up x% then down x% (either order) is always a net loss of x² ÷ 100 %.",
        _chained_same),
    Tip("reverse", "Reverse a percent", "Divide by the growth factor (after +20%: ÷ 1.2); don't take 20% off.",
        _reverse),
    Tip("pnl", "Round-trip P&L", "P&L = quantity × (sell − buy).", _pnl),
    Tip("pnl_multi", "Multi-fill P&L", "Price each sell against the buy and add: Σ qty × (sell − buy).", _pnl),
    Tip("pnl_marked", "Marked P&L", "Realized + unrealized: sold lots against the buy, the rest against the mark.",
        _pnl),
    Tip("vwap", "VWAP", "VWAP = low fill + gap × share of size at the high fill (each higher fill adds its own "
        "gap × share).", _vwap),
    Tip("spread", "Spread cost", "Crossing the spread costs (ask − bid) × quantity.", _spread),
    Tip("notional", "Notional", "Split the price: qty × whole dollars + qty × cents.", _notional),
)}

SUBTYPE_TIPS: dict[str, tuple[str, ...]] = {
    "add": ("add",), "sub": ("sub",), "mul": ("mul_split", "mul_25", "mul_5", "mul_11", "mul_9"), "div": ("div",),
    "frac_dec": ("quarters", "fifths", "eighths", "sixteenths"), "dec_frac": ("dec_frac",), "dec_int": ("dec_int",),
    "frac_pm": ("frac_pm",), "mixed": ("mixed",),
    "pct_of": ("pct_10", "pct_of"), "pct_change": ("pct_change",), "chained": ("chained", "chained_same"),
    "reverse": ("reverse",),
    "pnl": ("pnl", "pnl_multi", "pnl_marked"), "vwap": ("vwap",), "spread": ("spread",), "notional": ("notional",),
}


def render(key: str, problem: Problem | None = None) -> tuple[str, str, str | None]:
    """(title, general rule, worked example from `problem`'s own numbers — or None)."""
    tip = TIPS[key]
    example = tip.example(problem) if problem is not None and tip.example else None
    return tip.title, tip.rule, example
