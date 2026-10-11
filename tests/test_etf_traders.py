"""ETF Arb stage 3: computer traders — error sd, decision windows, the trade threshold, slow traders,
event trap avoidance, and determinism."""

import math
import random
from decimal import Decimal

import pytest

from met_games.games.etf.config import EASY, HARD, MEDIUM
from met_games.games.etf.engine import RECAP, RESULT, SKIP, YOU, EtfGame, Round, ticks
from met_games.games.etf.model import BUY, SELL, RoundPlan
from met_games.games.etf.traders import Plan, trader_decision

D = Decimal


# ── the decision rule ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "est,expected",
    [
        ("99.80", (None, 0)),  # buy gap 0.60 × 20 = 12.00 = fee + 2: not over
        ("99.81", (BUY, 20)),  # 0.61 × 20 = 12.20
        ("98.40", (None, 0)),  # sell gap 0.60 × 20 = 12.00
        ("98.39", (SELL, 20)),
        ("99.10", (None, 0)),  # inside the spread
    ],
)
def test_trade_threshold_boundary(est, expected):
    side, units, _ = trader_decision(D(est), D("99.00"), D("99.20"), 40, 40, 20, D(10))
    assert (side, units) == expected


def test_units_are_what_is_left_and_empty_side_skips():
    assert trader_decision(D("102"), D("99.00"), D("99.20"), 40, 7, 20, D(10))[:2] == (BUY, 7)  # 2.80 × 7 > 12
    assert trader_decision(D("100"), D("99.00"), D("99.20"), 40, 7, 20, D(10))[:2] == (None, 0)  # 0.80 × 7 = 5.6
    side, units, reason = trader_decision(D("102"), D("99.00"), D("99.20"), 40, 0, 20, D(10))
    assert side is None and "side empty" in reason


# ── pre-drawn behaviour ─────────────────────────────────────────────────────


@pytest.mark.parametrize("preset,sd", [(EASY, 1.00), (MEDIUM, 0.30), (HARD, 0.10)])
def test_error_sd_per_preset(preset, sd):
    errors = [float(p.error) for seed in range(250) for t in EtfGame(preset.replace(seed=seed)).traders.values()
              for p in t.plans]
    mean = sum(errors) / len(errors)
    est = math.sqrt(sum((e - mean) ** 2 for e in errors) / (len(errors) - 1))
    assert abs(mean) < 4 * sd / math.sqrt(len(errors))
    assert 0.94 * sd < est < 1.06 * sd


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_decision_times_fill_the_window(preset):
    times = {p.decide_tick for seed in range(150) for t in EtfGame(preset.replace(seed=seed)).traders.values()
             for p in t.plans}
    lo, hi = ticks(preset.decide_min), ticks(preset.decide_max)
    assert min(times) >= lo and max(times) <= hi
    assert min(times) <= lo + 2 and max(times) >= hi - 2  # spans the whole window


def test_trap_avoidance_rate():
    flags = [p.applies_event for seed in range(400) for t in EtfGame(HARD.replace(seed=seed)).traders.values()
             for p in t.plans]
    share = sum(flags) / len(flags)
    assert 0.68 < share < 0.72  # 70% apply events correctly


def test_trapped_trader_prices_with_the_shown_weights():
    seed = next(s for s in range(200) if EtfGame(HARD.replace(seed=s)).market.rounds[0].event)
    g = EtfGame(HARD.replace(seed=seed))
    plan = g.round.plan
    t = g.traders[1]
    t.plans[0] = Plan(t.plans[0].decide_tick, D(0), True)
    assert t.perceived_nav(1) == plan.nav
    t.plans[0] = Plan(t.plans[0].decide_tick, D(0), False)
    assert t.perceived_nav(1) == plan.naive_nav != plan.nav


# ── in the engine ────────────────────────────────────────────────────────────


def staged(est_errors, decide, size=40, cfg=EASY):
    """One round with NAV 100.00 and quote 99.00 @ 99.20; trader i decides at decide[i] ticks with error
    est_errors[i]."""
    g = EtfGame(cfg.replace(seed=1, size=size))
    plan = RoundPlan(1, ("AAPL",), (D(100),), (D(100),), (D(1),), (D(1),), None, D("0.90"), D("99.00"), D("99.20"))
    g.rounds[-1] = Round.open(plan, g.now, size)
    for (seat, t), err, at in zip(g.traders.items(), est_errors, decide):
        t.plans[0] = Plan(at, D(err), True)
    return g


def test_traders_race_and_deplete_the_shared_size():
    g = staged(["0", "0", "0"], [4, 8, 12], size=40)  # all see a 0.80 buy gap
    g.advance(20)
    fills = g.round.fills
    assert [(f.who, f.units, f.t) for f in fills] == [(1, 20, 4), (2, 20, 8)]
    third = g.round.decisions[3]
    assert third.action == SKIP and "side empty" in third.note
    assert fills[0].first and fills[0].bonus > 0 and not fills[1].first


def test_trader_past_the_timer_skips():
    timer = ticks(EASY.timer_s)
    g = staged(["0", "0", "0"], [timer, timer + 5, 1], size=40)
    g.skip()
    g.advance_to(g.round.start + timer)
    assert g.phase == RESULT
    for seat in (1, 2):
        d = g.round.decisions[seat]
        assert d.action == SKIP and d.t is None and "too slow" in d.note
    assert g.round.decisions[3].action == BUY


def test_wrong_way_on_a_noisy_estimate():
    g = staged(["-2.00", "0", "0"], [1, 50, 60])  # trader 1 thinks NAV is 98: sells into a buy round
    g.advance(2)
    f = g.round.fills[0]
    assert (f.who, f.side) == (1, SELL) and f.gross < 0


# ── determinism ──────────────────────────────────────────────────────────────


def run(seed, script):
    """Play a whole HARD session with scripted (delay ticks, action) per round on the tick clock."""
    g = EtfGame(HARD.replace(seed=seed))
    log = []
    for delay, action in script:
        g.advance(delay)
        if g.phase == "open":
            if action == "skip":
                g.skip()
            elif g.can_trade(YOU, action):
                g.trade(YOU, action, min(5, g.round.left(action)))
        g.advance_to(g.round.start + ticks(HARD.timer_s))
        log.append((g.round.plan, sorted((d.who, d.action, d.t, d.fill) for d in g.round.decisions.values())))
        g.next_round()
    assert g.phase == RECAP
    return [t.plans for t in g.traders.values()], log, [g.total(s) for s in range(4)]


def test_same_seed_same_inputs_same_session():
    script = [(3, BUY), (10, SELL), (0, "skip"), (6, BUY), (1, SELL), (2, "skip"), (20, BUY), (5, SELL)]
    assert run(11, script) == run(11, script)
    a, b = run(11, script), run(12, script)
    assert a != b


def test_computer_plans_do_not_depend_on_you():
    early = [(0, BUY)] * 8
    late = [(30, "skip")] * 8
    assert run(5, early)[0] == run(5, late)[0]  # same decision times, errors and event skill
