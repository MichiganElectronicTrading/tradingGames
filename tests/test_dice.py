"""Dice Game: exact fair value/range vs enumeration, 0.25 ticks, exact money, replay, config."""

import itertools
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from mtt_games.games.dice.config import EASY, HARD, MEDIUM, PRESETS, DiceConfig
from mtt_games.games.dice.engine import DICE, DiceRound, DiceSession, Die
from mtt_games.games.sumgame.engine import BUY, SELL, Decision, make_quote, risk_limits, trade_pnl
from mtt_games.games.sumgame.source import Market

D = Decimal
# Re-stated from the spec, independently of the engine's event table.
FACES = {
    None: (1, 2, 3, 4, 5, 6),
    "high_only": (5, 5, 5, 6, 6, 6),
    "one_is_seven": (7, 2, 3, 4, 5, 6),
    "six_is_zero": (1, 2, 3, 4, 5, 0),
    "evens_double": (1, 4, 3, 8, 5, 12),
    "odds_negative": (-1, 2, -3, 4, -5, 6),
    "double_hidden": (1, 2, 3, 4, 5, 6),
}
EVENTS = list(FACES)


def brute_force(up_faces, event, k):
    """Enumerate all 6^k hidden rolls (and, under double_hidden, every choice of doubled die)."""
    table = FACES[event]
    up = sum(table[f - 1] for f in up_faces)
    total, count = Fraction(0), 0
    lo = hi = None
    for roll in itertools.product(range(1, 7), repeat=k):
        vals = [table[f - 1] for f in roll]
        outs = [sum(vals) + v for v in vals] if event == "double_hidden" else [sum(vals)]
        total += Fraction(sum(outs), len(outs))
        count += 1
        lo = min(outs) if lo is None else min(lo, *outs)
        hi = max(outs) if hi is None else max(hi, *outs)
    if k == 0:
        return Fraction(up), up, up
    return up + total / count, up + lo, up + hi


def check(up_faces, event, k):
    m = DICE.market([Die(f) for f in up_faces], event, k)
    fair, lo, hi = brute_force(up_faces, event, k)
    assert Fraction(m.fair) == fair  # exact, not approximate
    assert (m.settle_min, m.settle_max) == (lo, hi)


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("k", [1, 2, 3, 4])
def test_zero_face_up_matches_enumeration(event, k):
    check([], event, k)


@pytest.mark.parametrize("event", EVENTS)
@pytest.mark.parametrize("up_faces", [[6], [1, 4], [2, 5, 3], [1, 6, 3, 5]])
def test_all_but_one_face_up_matches_enumeration(event, up_faces):
    check(up_faces, event, 1)


@pytest.mark.parametrize("event", EVENTS)
def test_mixed_face_up_matches_enumeration(event):
    check([3, 6], event, 3)
    check([1], event, 4)


def test_formulas_from_spec():
    m = DICE.market([Die(6), Die(1)], "odds_negative", 3)  # up = 6 + (-1) = 5, m = 0.5
    assert (m.fair, m.settle_min, m.settle_max) == (5 + 3 * 0.5, 5 - 15, 5 + 18)
    m = DICE.market([Die(2)], "double_hidden", 2)  # (k+1) draws of the standard die
    assert (m.fair, m.settle_min, m.settle_max) == (2 + 3 * 3.5, 2 + 3, 2 + 18)


# ── ticks ────────────────────────────────────────────────────────────────────


def on_tick(x):
    return isinstance(x, Decimal) and x % D("0.25") == 0


def test_quotes_snap_to_quarter_ticks():
    rng = random.Random(3)
    for _ in range(5000):
        spread = D("0.25") * rng.randint(1, 32)
        bid, ask = make_quote(rng.uniform(-40, 80), rng.gauss(0, 2), spread, D("0.25"))
        assert on_tick(bid) and on_tick(ask)
        assert ask - bid == spread  # exact, Decimal arithmetic


def test_quote_rounds_to_nearest_tick():
    assert make_quote(18.3, 0.0, D("1.00"), D("0.25")) == (D("17.75"), D("18.75"))  # 17.8 → 17.75
    assert make_quote(18.0, 0.2, D("2.00"), D("0.25")) == (D("17.25"), D("19.25"))  # 17.2 → 17.25


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_session_quotes_on_tick_with_exact_spread(preset):
    for seed in range(30):
        s = DiceSession(preset.replace(seed=seed))
        while not s.finished:
            rnd = s.new_round()
            if rnd is None:
                break
            if rnd.flip_at is not None:
                s.advance(rnd.flip_at)
            for _, bid, ask in rnd.tape:
                assert on_tick(bid) and on_tick(ask) and ask - bid == preset.spread
            s.pass_(rnd.timer_s / 2)


# ── P&L reports to the cent ─────────────────────────────────────────────────


def session_with_pnl(settle_faces, action, bid, ask, size=1):
    """A dice session whose only round is decided, with a known P&L."""
    s = DiceSession(EASY.replace(seed=1))
    rnd = DiceRound(1, [Die(f) for f in settle_faces], None, list(range(len(settle_faces))), None, 60, D("500"))
    rnd.tape.append((0.0, bid, ask))
    rnd.decision = Decision(action, size, 1.0, bid, ask, Market(0, 0, 3.5, 6, False, 18.0, 0, 0), 10, 10)
    s.rounds.append(rnd)
    return s, rnd


@pytest.mark.parametrize(
    "report,correct",
    [("17.5", True), ("17.50", True), ("17.499", True), ("17.495", True), (D("17.50"), True), (17.5, True),
     ("17.494", False), ("17.49", False), ("18", False), ("-17.50", False)],
)
def test_decimal_reports_compare_to_the_cent(report, correct):
    s, rnd = session_with_pnl([6, 6, 6], BUY, D("0.25"), D("0.50"))  # settle 18 − 0.50 = 17.50
    assert rnd.pnl == D("17.50")
    assert s.report(report, 2.0) is correct
    assert rnd.report_correct is correct


def test_non_numeric_report_rejected_without_recording():
    s, rnd = session_with_pnl([6, 6, 6], BUY, D("0.25"), D("0.50"))
    with pytest.raises(ValueError):
        s.report("abc", 1.0)
    assert rnd.reported is None


# ── risk + P&L with fractional prices ───────────────────────────────────────


def test_risk_limits_with_fractional_prices():
    # worst per unit 18.75 − 6 = 12.75 and 30 − 17.25 = 12.75 → ⌊500 / 12.75⌋ = 39
    assert risk_limits(D("500"), D("17.25"), D("18.75"), 6, 30) == (39, 39)
    # exact boundary that float division gets wrong (25.5 / 12.75 = 2 exactly)
    assert risk_limits(D("25.50"), D("17.25"), D("18.75"), 6, 30) == (2, 2)
    assert risk_limits(D("12.50"), D("17.25"), D("18.75"), 6, 30) == (0, 0)  # both sides disabled
    assert risk_limits(D("5"), D("5.50"), D("5.75"), 6, 30) == (100, 0)  # ask below min settle: riskless long
    assert risk_limits(D("1000"), D("17.25"), D("18.75"), 18, 19) == (100, 100)  # capped


def test_pnl_with_fractional_prices_is_exact():
    assert trade_pnl(BUY, 3, D("17.25"), D("18.75"), 20) == D("3.75")
    assert trade_pnl(SELL, 2, D("17.25"), D("18.75"), 20) == D("-5.50")
    s, rnd = session_with_pnl([1, 2], SELL, D("4.75"), D("5.25"), size=4)  # (4.75 − 3) × 4 = 7.00
    assert rnd.pnl == D("7.00") and rnd.verdict


def test_balances_stay_exact_over_many_rounds():
    for seed in range(40):
        s = DiceSession(HARD.replace(seed=seed, rounds=20))
        total = D("0")
        while not s.finished:
            rnd = s.new_round()
            if rnd is None:
                break
            max_long, max_short = s.limits()
            if seed % 2 and max_long >= 1:
                s.buy(min(3, max_long), 1.0)
            elif max_short >= 1:
                s.sell(min(3, max_short), 1.0)
            else:
                s.pass_(1.0)
            total += rnd.pnl
            assert isinstance(s.balance, Decimal) and s.balance % D("0.25") == 0
            assert s.report(str(rnd.pnl), 1.0) is True  # the exact P&L text is always a correct report
        assert s.balance == D("500") + total


# ── replay + config ─────────────────────────────────────────────────────────


def _play(cfg, script):
    s = DiceSession(cfg)
    trace = []
    for action, t in script:
        rnd = s.new_round()
        s.advance(t / 2)
        if action == "buy" and s.limits()[0] >= 1:
            s.buy(1, t)
        elif action == "sell" and s.limits()[1] >= 1:
            s.sell(1, t)
        else:
            s.pass_(t)
        s.report(str(rnd.pnl), 1.0)
        trace.append((
            [d.face for d in rnd.dice], list(rnd.face_up), rnd.event, rnd.doubled, rnd.flip_at, rnd.flip_index,
            rnd.flipped_at, rnd.flip_stale, list(rnd.tape), rnd.decision, rnd.settle, rnd.pnl,
        ))
    return s.seed, s.balance, trace


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_same_seed_same_dice_session(preset):
    script = [("buy", 9.0), ("sell", 3.0), ("pass", 12.0), ("buy", 14.0)]
    cfg = preset.replace(seed=77, rounds=4)
    assert _play(cfg, script) == _play(cfg, script)
    assert _play(cfg, script) != _play(preset.replace(seed=78, rounds=4), script)


def test_dice_are_independent_rolls():
    s = DiceSession(EASY.replace(seed=5, rounds=20, n_dice_min=10, n_dice_max=10, face_up_max=0))
    faces = []
    for _ in range(20):
        rnd = s.new_round()
        faces += [d.face for d in rnd.dice]
        s.pass_(0.1)
    assert max(faces.count(f) for f in range(1, 7)) > 4  # more repeats than a 4-per-rank deck allows


def test_presets_match_table():
    assert (EASY.n_dice_min, EASY.spread, EASY.quote_noise_sd, EASY.sizing) == (3, D("2.00"), 1.5, "fixed")
    assert (MEDIUM.n_dice_max, MEDIUM.face_up_max, MEDIUM.timer_s, MEDIUM.spread, MEDIUM.quote_noise_sd) == (
        5, 2, 30, D("1.50"), 1.0)
    assert (HARD.n_dice_min, HARD.n_dice_max, HARD.face_up_min, HARD.face_up_max) == (6, 8, 1, 3)
    assert (HARD.spread, HARD.quote_noise_sd, HARD.rounds, HARD.timer_s) == (D("1.00"), 0.75, 6, 15)
    assert HARD.mid_round_flip and HARD.stale_quotes and HARD.event_freq == 1.0 and len(HARD.enabled_events) == 6
    assert all(p.budget == 500 and not p.errors() for p in PRESETS.values())


@pytest.mark.parametrize("spread", [D("0"), D("2.10"), D("8.25"), D("-0.25")])
def test_spread_must_be_whole_ticks_in_range(spread):
    with pytest.raises(ValueError):
        EASY.replace(spread=spread).validate()


@pytest.mark.parametrize("spread", [D("0.25"), D("1.75"), D("8.00")])
def test_valid_spreads(spread):
    EASY.replace(spread=spread).validate()


def test_dice_config_validation_and_round_trip():
    assert EASY.replace(face_up_max=4).errors()  # face-up max > dice min
    assert EASY.replace(enabled_events=("face_ten",), event_freq=1.0).errors()  # a card event
    assert DiceConfig.from_dict(HARD.to_dict()) == HARD


def test_config_settle_range():
    assert DICE.settle_range(EASY) == (3, 18)
    lo, hi = DICE.settle_range(HARD)
    assert (lo, hi) == (8 * -5, 8 * 12)  # eight dice: all −5 under odds_negative, all 12 under evens_double
