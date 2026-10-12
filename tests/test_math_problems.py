"""Mental Math problem engine: determinism, exact answers recomputed independently, dp limits, operand bounds,
desk worked cases, answer parsing and the Zetamac standard ranges."""

import random
from fractions import Fraction as F

import pytest

from met_games.games.math.problems import (
    BASE,
    CORE,
    DECFRAC,
    DESK,
    EASY,
    FAMILIES,
    FRACTION,
    HARD,
    LEVELS,
    MAX_PLACES,
    MEDIUM,
    PCT,
    SUBTYPES,
    ZETAMAC,
    Problem,
    ProblemStream,
    ZetamacStream,
    accepts,
    dec,
    fills_pnl,
    make,
    parse_answer,
    vwap,
    within_difficulty,
)

N = 1500  # problems per family × difficulty


def recompute(p: Problem) -> F:
    """The answer from the operands, written independently of the generator."""
    o = p.operands
    s = p.subtype
    if s == "add":
        return F(o[0]) + F(o[1])
    if s == "sub":
        return F(o[0]) - F(o[1])
    if s == "mul":
        return F(o[0]) * F(o[1])
    if s == "div":
        assert o[0] % o[1] == 0
        return F(o[0], o[1])
    if s in ("frac_dec", "dec_frac"):
        return o[0]
    if s == "dec_int":
        return o[0] * o[1]
    if s in ("frac_pm", "mixed"):
        return o[0] + o[2] if o[1] == "+" else o[0] - o[2]
    if s == "pct_of":
        return F(o[0] * o[1], 100)
    if s == "pct_change":
        return F(o[1] - o[0], o[0]) * 100
    if s == "chained":
        return ((1 + F(o[0], 100)) * (1 + F(o[1], 100)) - 1) * 100
    if s == "reverse":
        return o[1] / (1 + F(o[0], 100))
    if s == "pnl":
        fills, mark = o
        bought = sum(q * px for q, px in fills if q > 0)
        sold = sum(-q * px for q, px in fills if q < 0)
        open_qty = sum(q for q, _ in fills)
        return sold - bought + (open_qty * mark if open_qty else 0)
    if s == "spread":
        bid, ask, q = o
        return (ask - bid) * q
    if s == "notional":
        return o[0] * o[1]
    if s == "vwap":
        return sum(q * px for q, px in o) / sum(q for q, _ in o)
    raise AssertionError(s)


def terminates_within(x: F, k: int) -> bool:
    return (x * 10**k).denominator == 1


def check_bounds(p: Problem) -> None:
    o, s, lv = p.operands, p.subtype, p.level
    if s in ("add", "sub"):
        lo, hi = {EASY: (10, 99), MEDIUM: (100, 999), HARD: (1000, 9999)}[lv]
        assert lo <= o[0] <= hi and lo <= o[1] <= hi
        if s == "sub":
            assert o[0] > o[1]
    elif s == "mul":
        a, b = o
        if lv == EASY:
            assert 2 <= a <= 12 and 2 <= b <= 12
        elif lv == MEDIUM:
            assert (10 <= a <= 99 and 10 <= b <= 99) or (100 <= a <= 999 and 2 <= b <= 9)
        else:
            assert 100 <= a <= 999 and 10 <= b <= 99
    elif s == "div":
        n, d = o
        q = n // d
        if lv == EASY:
            assert 2 <= d <= 12 and 2 <= q <= 12 and n <= 144
        elif lv == MEDIUM:
            assert 2 <= d <= 9 and 100 <= n <= 999
        else:
            assert 10 <= d <= 99 and 100 <= n <= 9999
    elif s in ("frac_dec", "dec_frac"):
        assert o[0].denominator in {EASY: (2, 4, 5), MEDIUM: (8,), HARD: (16,)}[lv] and 0 < o[0] < 1
    elif s == "dec_int":
        m, k = o
        assert m.denominator in {EASY: (2, 4), MEDIUM: (8,), HARD: (16,)}[lv] and 8 <= k <= 120
    elif s == "frac_pm":
        assert lv == MEDIUM and o[0].denominator <= 16 and o[2].denominator <= 16 and p.answer > 0
    elif s == "mixed":
        assert lv == HARD and {o[0].denominator, o[2].denominator} <= {8, 16} and p.answer > 0
    elif s == "pct_of":
        pc, n = o
        if lv == EASY:
            assert pc in (10, 25, 50) and n % 20 == 0 and p.answer.denominator == 1
        else:
            assert 1 <= pc <= 99 and 20 <= n <= 990 and terminates_within(p.answer, 1)
    elif s == "pct_change":
        assert p.answer.denominator == 1 and -50 <= p.answer <= 100 and p.answer != 0
    elif s == "chained":
        assert all(5 <= abs(x) <= 50 for x in o) and o[0] * o[1] < 0
    elif s == "reverse":
        assert o[0] % 5 == 0 and o[0] != 0 and 20 <= p.answer <= 2000
    elif s in ("pnl", "vwap"):
        fills = o[0] if s == "pnl" else o
        for q, px in fills:
            assert q % 100 == 0 and q != 0 and terminates_within(px, 2)
            if lv == EASY:
                assert px.denominator == 1 and 10 <= px <= 99
            else:
                assert 10 <= px <= 100
        if lv in (EASY, MEDIUM):
            assert all(100 <= abs(q) <= 900 for q, _ in fills)
        if s == "pnl" and o[1] is None:
            assert sum(q for q, _ in fills) == 0  # round trip: flat at the end
        if s == "pnl" and lv in (EASY, MEDIUM):
            assert len(fills) == 2 and price_diff_ok(fills[1][1] - fills[0][1], lv)
        if s == "vwap" and lv == MEDIUM:
            (q1, _), (q2, _) = fills
            assert len(fills) == 2 and max(q1, q2) in (min(q1, q2), 2 * min(q1, q2))
    elif s == "spread":
        bid, ask, q = o
        assert 100 <= q <= 900 and q % 100 == 0 and price_diff_ok(ask - bid, lv)
    elif s == "notional":
        q, px = o
        assert 100 <= q <= 900 and q % 100 == 0
        if lv == EASY:
            assert px.denominator == 1 and str(px).rstrip("0") in "123456789" and len(str(px).rstrip("0")) == 1
        else:
            assert (px * 10).denominator == 1 and 10 <= px < 100


def price_diff_ok(d: F, lv: str) -> bool:
    """EASY: whole dollars 1–9; MEDIUM: a multiple of 0.05 up to 0.95."""
    d = abs(d)
    if lv == EASY:
        return d.denominator == 1 and 1 <= d <= 9
    return (d * 20).denominator == 1 and 0 < d <= F("0.95")


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("level", LEVELS)
def test_thousands_of_problems_are_exact_bounded_and_terminate(family, level):
    rng = random.Random(f"{family}-{level}")
    seen = set()
    for _ in range(N):
        p = make(rng, family, level)
        assert p.family == family and p.level == level and p.subtype in SUBTYPES[family][level]
        assert isinstance(p.answer, F)
        assert recompute(p) == p.answer, p
        assert terminates_within(p.answer, MAX_PLACES[family]), p
        assert p.base == BASE[family]
        check_bounds(p)
        assert accepts(p, p.answer_text)
        seen.add(p.subtype)
    assert seen == set(SUBTYPES[family][level])  # every subtype turns up


def test_same_seed_same_problems_and_families_drawn_evenly():
    a = [ProblemStream(42).next() for _ in range(1)]
    s1, s2 = ProblemStream(42), ProblemStream(42)
    first = [s1.next() for _ in range(100)]
    assert first == [s2.next() for _ in range(100)]
    assert a[0] == first[0]
    assert [p.text for p in first] != [p.text for p in (ProblemStream(43).next() for _ in range(100))]
    counts = {f: sum(p.family == f for p in first) for f in FAMILIES}
    assert counts == {f: 25 for f in FAMILIES}  # shuffled bags: exactly even over whole bags


def test_stream_weights_levels_and_pool():
    s = ProblemStream(1, families=(CORE, DESK), weights={CORE: 3, DESK: 1}, levels={CORE: HARD, DESK: EASY})
    ps = [s.next() for _ in range(40)]
    assert sum(p.family == CORE for p in ps) == 30
    assert all(p.level == (HARD if p.family == CORE else EASY) for p in ps)
    drill = ProblemStream(1, pool=[(CORE, "mul"), (PCT, "pct_change")], level=MEDIUM)
    assert {(p.family, p.subtype) for p in (drill.next() for _ in range(20))} == {(CORE, "mul"), (PCT, "pct_change")}
    with pytest.raises(ValueError):
        ProblemStream(1, families=())


# ── desk worked cases ───────────────────────────────────────────────────────


def test_multi_fill_pnl():
    # bought 300 @ 42.15, sold 200 @ 42.40 and 100 @ 42.05 → 200 × 0.25 − 100 × 0.10 = 40
    fills = ((300, F("42.15")), (-200, F("42.40")), (-100, F("42.05")))
    assert fills_pnl(fills) == 40


def test_vwap_of_two_and_three_fills():
    assert vwap(((200, F("42.10")), (300, F("42.20")))) == F("42.16")
    assert vwap(((100, F("10.00")), (100, F("10.10")), (200, F("10.20")))) == F("10.125")


def test_spread_cost():
    p = make(random.Random(5), DESK, MEDIUM, "spread")
    bid, ask, q = p.operands
    assert p.answer == (ask - bid) * q
    assert (F("42.15") - F("42.10")) * 300 == 15  # 42.10 / 42.15, buy 300 at the ask, sell at the bid


def test_marked_pnl():
    # bought 500 @ 42.15, sold 300 @ 42.40, mark 42.30 → 300 × 0.25 + 200 × 0.15 = 105
    fills = ((500, F("42.15")), (-300, F("42.40")))
    assert fills_pnl(fills, F("42.30")) == 105


def test_desk_text_reads_like_the_desk():
    rng = random.Random(9)
    texts = {make(rng, DESK, HARD).tip_key: None for _ in range(200)}
    assert {"pnl_multi", "pnl_marked", "vwap"} <= set(texts)
    p = make(random.Random(3), DESK, MEDIUM, "notional")
    assert p.text == f"notional of {p.operands[0]} @ {dec(p.operands[1], 2)}"


# ── answer input ────────────────────────────────────────────────────────────


def prob(answer, form="any"):
    return Problem("?", F(answer), DECFRAC, "frac_pm", MEDIUM, "frac_pm", (), form)


def test_fraction_and_decimal_are_equivalent():
    p = prob("13/16")
    assert accepts(p, "13/16") and accepts(p, "0.8125") and accepts(p, ".8125") and accepts(p, "26/32")


def test_leading_point_and_negatives():
    assert parse_answer(".5") == F(1, 2)
    assert accepts(prob("0.5"), ".5")
    assert parse_answer("-1.25") == F(-5, 4) and parse_answer("-.25") == F(-1, 4) and parse_answer("-3/8") == F(-3, 8)
    assert accepts(prob("-12.5"), "-12.5") and not accepts(prob("12.5"), "-12.5")


def test_no_lock_on_an_unequal_prefix_and_lock_exactly_on_equality():
    p = prob("1.25")
    typed = ""
    locks = []
    for ch in "1.25":
        typed += ch
        locks.append(accepts(p, typed))
    assert locks == [False, False, False, True]
    assert [parse_answer(t) for t in ("", "-", ".", "-.", "1/", "/2", "1/0", "1.2.3", "1/2/3", "1.5/2")] == [None] * 10
    assert not accepts(prob("12"), "1") and accepts(prob("12"), "12")


def test_answer_forms():
    frac_dec = Problem("3/8 as a decimal", F(3, 8), DECFRAC, "frac_dec", MEDIUM, "eighths", (F(3, 8),), "decimal")
    assert accepts(frac_dec, "0.375") and accepts(frac_dec, ".375") and not accepts(frac_dec, "3/8")
    dec_frac = Problem("0.375 as a fraction", F(3, 8), DECFRAC, "dec_frac", MEDIUM, "dec_frac", (F(3, 8),), FRACTION)
    assert accepts(dec_frac, "3/8") and accepts(dec_frac, "6/16") and not accepts(dec_frac, "0.375")


def test_dec_formatting():
    assert dec(F(3, 8)) == "0.375" and dec(F(-3, 2)) == "-1.5" and dec(F(421, 10), 2) == "42.10" and dec(7) == "7"


# ── Zetamac standard ────────────────────────────────────────────────────────


def test_zetamac_ranges_and_operations_exact():
    s = ZetamacStream(11)
    ops = set()
    for _ in range(5000):
        p = s.next()
        a, b = p.operands
        ops.add(p.subtype)
        assert p.level == ZETAMAC and p.family == CORE
        if p.subtype == "add":
            assert 2 <= a <= 100 and 2 <= b <= 100 and p.answer == a + b and p.text == f"{a} + {b}"
        elif p.subtype == "sub":  # (a + b) − a = b
            assert 2 <= b <= 100 and 2 <= a - b <= 100 and p.answer == a - b and 2 <= p.answer <= 100
        elif p.subtype == "mul":
            assert 2 <= a <= 12 and 2 <= b <= 100 and p.answer == a * b and p.text == f"{a} × {b}"
        else:  # (a × b) ÷ a = b
            assert 2 <= b <= 12 and a % b == 0 and 2 <= p.answer <= 100 and p.answer == a // b
    assert ops == {"add", "sub", "mul", "div"}


# ── the difficulty ceiling ──────────────────────────────────────────────────

CEILING_N = 5000


def digits_of(x: F) -> int:
    """x written out without sign, decimal point or trailing zeros (0.25 → 25, 300 → 3), independently of the engine."""
    text = dec(abs(x)).replace(".", "").lstrip("0").rstrip("0")
    return int(text or "0")


def do_step(op: str, a, b) -> F:
    a, b = F(a), F(b)
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    assert op in ("div", "frac")
    return a / b


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("level", LEVELS)
def test_five_thousand_problems_stay_within_their_difficulty(family, level):
    rng = random.Random(f"ceiling-{family}-{level}")
    for _ in range(CEILING_N):
        p = make(rng, family, level)
        assert p.steps and within_difficulty(p.steps, level), p
        results = [do_step(*step) for step in p.steps]
        assert results[-1] == p.answer, p  # the steps, worked by hand, reach the stored answer


def test_easy_desk_steps_are_one_digit_times_one_digit():
    rng = random.Random("easy-desk")
    for _ in range(CEILING_N):
        p = make(rng, DESK, EASY)
        for op, a, b in p.steps:
            if op == "mul":
                assert digits_of(F(a)) <= 9 and digits_of(F(b)) <= 9, p  # never 2-digit × 2-digit or bigger
        assert p.tip_key not in ("vwap", "pnl_multi", "pnl_marked")


def test_the_ceiling_rules():
    assert within_difficulty([("mul", 12, 12)], EASY) and not within_difficulty([("mul", 13, 12)], EASY)
    # decimal points and ×100 lot sizes don't count: 0.25 × 300 is 25 × 3 — past 12×12, fine at MEDIUM
    assert not within_difficulty([("mul", F("0.25"), 300)], EASY)
    assert within_difficulty([("mul", F("0.25"), 300)], MEDIUM)
    assert within_difficulty([("mul", 300, 4)], EASY)  # 3 × 4, then zeros
    assert within_difficulty([("mul", 4237, 100)], EASY) and within_difficulty([("div", 4237, 100)], EASY)  # shifts
    assert within_difficulty([("mul", 99, 99)], MEDIUM) and within_difficulty([("mul", 999, 9)], MEDIUM)
    assert not within_difficulty([("mul", 999, 99)], MEDIUM) and within_difficulty([("mul", 999, 99)], HARD)
    assert not within_difficulty([("mul", 9999, 9)], HARD)
    assert within_difficulty([("div", 144, 12)], EASY) and not within_difficulty([("div", 156, 12)], EASY)
    assert within_difficulty([("add", 99, 99)], EASY) and not within_difficulty([("add", 123, 456)], EASY)
    assert within_difficulty([("sub", 9999, 1234)], HARD) and not within_difficulty([("add", 10000, 12345)], HARD)
    assert within_difficulty([("sub", F("42.62"), F("42.37"))], EASY)  # shared 42: it's 62 − 37
    assert within_difficulty([("add", F("42.37"), F("0.25"))], EASY)  # only the cents columns work
    assert not within_difficulty([("sub", F("50.85"), F("49.90"))], MEDIUM)
    assert not within_difficulty([("div", 1, 3)], HARD)  # never terminates
    assert within_difficulty([("mul", 10**6, 10**6)], ZETAMAC)  # no ceiling outside easy / medium / hard


def test_worked_easy_desk():
    # bought 300 @ 42, sold @ 45 → (45 − 42) × 300 = 3 × 3, add zeros = 900
    steps = [("sub", 45, 42), ("mul", 3, 300)]
    assert within_difficulty(steps, EASY) and do_step(*steps[-1]) == 900
    assert fills_pnl(((300, F(42)), (-300, F(45)))) == 900
    p = make(random.Random(4), DESK, EASY, "pnl")
    (q, b), (_, s) = p.operands[0]
    assert p.text == f"bought {q} @ {b}, sold @ {s}: P&L" and p.answer == (s - b) * q
    assert make(random.Random(4), DESK, EASY, "notional").answer % 100 == 0
    assert not within_difficulty([("mul", 300, 42)], EASY)  # a 2-digit price × size is MEDIUM work


def test_worked_medium_desk():
    # bought 300 @ 42.37, sold @ 42.62 → 0.25 × 300 = 75
    steps = [("sub", F("42.62"), F("42.37")), ("mul", F("0.25"), 300)]
    assert within_difficulty(steps, MEDIUM) and not within_difficulty(steps, EASY)
    assert fills_pnl(((300, F("42.37")), (-300, F("42.62")))) == 75
    # VWAP 300 @ 42.10, 600 @ 42.40: 2:1 toward the bigger fill → 42.10 + 2 × (0.30 ÷ 3) = 42.30
    fills = ((300, F("42.10")), (600, F("42.40")))
    steps = [("sub", F("42.40"), F("42.10")), ("div", F("0.30"), 3), ("mul", F("0.10"), 2), ("add", F("42.10"),
                                                                                          F("0.20"))]
    assert within_difficulty(steps, MEDIUM) and do_step(*steps[-1]) == vwap(fills) == F("42.30")
    # notional ≤ 3-digit × 1-digit: 400 @ 42.10 = 421 × 4, zeros
    assert within_difficulty([("mul", 400, F("42.10"))], MEDIUM)
    assert not within_difficulty([("mul", 400, F("42.37"))], MEDIUM)
    seen = {make(random.Random(n), DESK, MEDIUM, "vwap").operands for n in range(50)}
    assert all(len(f) == 2 for f in seen)


def test_worked_hard_desk():
    # bought 300 @ 42.15, sold 200 @ 42.40 and 100 @ 42.05 → 200 × 0.25 + 100 × (−0.10) = 40
    steps = [("sub", F("42.40"), F("42.15")), ("mul", F("0.25"), 200), ("sub", F("42.05"), F("42.15")),
             ("mul", F("-0.10"), 100), ("add", 50, -10)]
    assert within_difficulty(steps, HARD) and do_step(*steps[-1]) == 40
    # 3-fill VWAP 200 @ 42.10, 300 @ 42.20, 500 @ 42.30: offsets from 42.10 → (300 × 0.10 + 500 × 0.20) ÷ 1000
    fills = ((200, F("42.10")), (300, F("42.20")), (500, F("42.30")))
    steps = [("sub", F("42.20"), F("42.10")), ("mul", 300, F("0.10")), ("sub", F("42.30"), F("42.10")),
             ("mul", 500, F("0.20")), ("add", 30, 100), ("add", 200, 300), ("add", 500, 500), ("div", 130, 1000),
             ("add", F("42.10"), F("0.13"))]
    assert within_difficulty(steps, HARD) and do_step(*steps[-1]) == vwap(fills) == F("42.23")
    kinds = {make(random.Random(n), DESK, HARD).tip_key for n in range(200)}
    assert {"pnl_multi", "pnl_marked", "vwap"} <= kinds
