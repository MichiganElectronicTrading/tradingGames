"""ETF Arb stage 1: basket, prices, quotes, events and exact NAV."""

import math
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from met_games.games.etf.config import EASY, HARD, MEDIUM, PRESETS, EtfConfig
from met_games.games.etf.model import (
    REBAL,
    REVERSE,
    SPLIT,
    TICKERS,
    draw_market,
    draw_weights,
    nav,
    quote,
    to_tick,
)

D = Decimal


def markets(cfg, seeds=range(200)):
    return [draw_market(cfg, random.Random(s)) for s in seeds]


# ── basket ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", list(PRESETS))
def test_weights_sum_to_exactly_one_in_the_right_format(name):
    cfg = PRESETS[name]
    for m in markets(cfg):
        w = m.start_weights
        assert len(w) == cfg.stocks and sum(w) == D(1)  # exact Decimal equality
        assert all(isinstance(x, Decimal) for x in w)
        if cfg.weight_places == 1:
            assert all(x >= D("0.1") and x == x.quantize(D("0.1")) for x in w)
        else:
            assert all(x >= D("0.05") and x == x.quantize(D("0.01")) for x in w)
        assert len(set(m.tickers)) == cfg.stocks and set(m.tickers) <= set(TICKERS)


def test_weight_compositions_vary():
    seen = {tuple(draw_weights(random.Random(s), 4, 1, D("0.1"))) for s in range(300)}
    assert len(seen) > 30  # many different baskets, not one fixed split


@pytest.mark.parametrize("name,tick", [("EASY", D("1")), ("MEDIUM", D("0.1")), ("HARD", D("0.01"))])
def test_prices_on_the_tick_and_in_range(name, tick):
    cfg = PRESETS[name]
    for m in markets(cfg, range(100)):
        assert all(D(50) <= p <= D(600) and p == p.quantize(tick) for p in m.start_prices)
        for plan in m.rounds:
            assert all(p == p.quantize(tick) and p > 0 for p in plan.prices)


def test_moves_are_small_and_about_one_in_five_stocks_stay_put():
    cfg = MEDIUM.replace(rounds=20)
    still = total = 0
    rel = []
    for m in markets(cfg, range(150)):
        for plan in m.rounds:
            for prev, p in zip(plan.prev_prices, plan.prices):
                total += 1
                if p == prev:
                    still += 1
                else:
                    rel.append(float((p - prev) / prev))
    assert 0.17 < still / total < 0.25  # 20% still, plus a few moves that round to zero
    sd = (sum(x * x for x in rel) / len(rel)) ** 0.5
    assert 0.0055 < sd < 0.0065  # sd 0.6% of price


TICKS = {"EASY": D("1"), "MEDIUM": D("0.1"), "HARD": D("0.01")}


@pytest.mark.parametrize("name", list(PRESETS))
def test_nav_is_the_exact_sum_of_w_x_p_at_the_difficulty_tick(name):
    tick = TICKS[name]
    for m in markets(PRESETS[name], range(50)):
        for plan in m.rounds:
            assert plan.tick == tick
            rows = [(Fraction(w) * Fraction(p) / Fraction(tick)) for w, p in zip(plan.weights, plan.prices)]
            exact = sum(Fraction(math.floor(r + Fraction(1, 2))) * Fraction(tick) for r in rows)  # half-up per row
            assert isinstance(plan.nav, Decimal) and Fraction(plan.nav) == exact
            assert plan.nav == plan.nav.quantize(tick)  # whole / tenths / cents


def test_same_seed_same_market():
    for cfg in (EASY, MEDIUM, HARD):
        assert draw_market(cfg, random.Random(9)) == draw_market(cfg, random.Random(9))
        assert draw_market(cfg, random.Random(9)) != draw_market(cfg, random.Random(10))


# ── quotes ───────────────────────────────────────────────────────────────────


def test_quote_examples():
    assert quote(D("237.50"), D("4.00")) == (D("233.40"), D("233.60"))  # cents: mid 233.50 ± 0.10
    assert quote(D("100.12"), D("-1.00")) == (D("101.02"), D("101.22"))
    assert quote(D("328.7"), D("0.33"), D("0.1")) == (D("328.3"), D("328.5"))  # tenths: 328.27 → 328.3
    assert quote(D("320"), D("-2.60"), D("1")) == (D("322"), D("323"))  # whole dollars: $1 wide


@pytest.mark.parametrize("name,width", [("EASY", D("1")), ("MEDIUM", D("0.2")), ("HARD", D("0.20"))])
def test_quotes_on_the_difficulty_tick(name, width):
    tick = TICKS[name]
    for m in markets(PRESETS[name], range(50)):
        for plan in m.rounds:
            assert plan.ask - plan.bid == width
            assert plan.bid == plan.bid.quantize(tick) and plan.ask == plan.ask.quantize(tick)
            assert str(plan.ask) == str(plan.ask.quantize(tick))  # printed at that precision too
            assert plan.bid == to_tick(plan.nav - plan.gap - width / 2, tick)


@pytest.mark.parametrize("name,chance,lo,hi", [("EASY", 0.15, "1.20", "3.50"), ("MEDIUM", 0.22, "0.70", "3.00"),
                                               ("HARD", 0.25, "0.55", "3.00")])
def test_gap_distribution_has_skip_and_trade_rounds_and_is_symmetric(name, chance, lo, hi):
    gaps = [plan.gap for m in markets(PRESETS[name].replace(rounds=20), range(300)) for plan in m.rounds]
    small = [g for g in gaps if abs(g) <= D("0.45")]
    big = [g for g in gaps if D(lo) <= abs(g) <= D(hi)]
    assert len(small) + len(big) == len(gaps)  # nothing between the bands
    assert chance - 0.03 < len(small) / len(gaps) < chance + 0.03
    positive = sum(1 for g in gaps if g > 0)
    assert 0.46 < positive / len([g for g in gaps if g != 0]) < 0.54  # 50/50 sign


def test_right_call_skips_are_rarest_on_easy():
    """Trade rounds are most common on EASY, then MEDIUM; HARD keeps the original ~1 in 4 skip rounds."""
    from met_games.games.etf.model import right_call

    def skip_share(cfg):
        plans = [p for m in markets(cfg.replace(rounds=10), range(400)) for p in m.rounds]
        return sum(right_call(p.nav, p.bid, p.ask, min(20, cfg.size), cfg.fee)[0] == "SKIP" for p in plans) / len(plans)

    easy, medium, hard = skip_share(EASY), skip_share(MEDIUM), skip_share(HARD)
    assert 0.12 < easy < 0.20 and 0.18 < medium < 0.26 and 0.23 < hard < 0.31
    assert easy < medium < hard


@pytest.mark.parametrize("name", list(PRESETS))
def test_last_nav_plus_the_change_column_is_exactly_the_new_nav(name):
    """last NAV + Σ Δ W × P = Σ W × P, every round — the shortcut you can do from the table."""
    for m in markets(PRESETS[name], range(150)):
        for plan in m.rounds:
            rows = range(len(plan.tickers))
            assert m.nav_before(plan.number) + sum(plan.wxp_change(i) for i in rows) == plan.naive_nav
            assert m.nav_before(plan.number) + sum(plan.wxp_change(i, adjusted=True) for i in rows) == plan.nav


def test_summing_raw_chg_is_not_the_nav_change():
    """Why the plain CHG column can't be summed: NAV moves by weight × CHG, not CHG."""
    m = draw_market(EASY, random.Random(7))
    plan = m.rounds[1]
    raw = sum(p - q for p, q in zip(plan.prices, plan.prev_prices))
    assert m.nav_before(2) + raw != plan.nav or raw == 0


# ── events ───────────────────────────────────────────────────────────────────


def event_rounds(cfg=HARD, seeds=range(400)):
    for m in markets(cfg, seeds):
        for i, plan in enumerate(m.rounds):
            if plan.event:
                yield m, i, plan


def test_events_hard_only_and_about_one_in_three():
    assert not any(p.event for m in markets(EASY) + markets(MEDIUM) for p in m.rounds)
    plans = [p for m in markets(HARD, range(300)) for p in m.rounds]
    share = sum(1 for p in plans if p.event) / len(plans)
    assert 0.30 < share < 0.37


def test_split_reverse_and_rebalance_nav():
    kinds = set()
    for m, i, plan in event_rounds():
        e = plan.event
        k = plan.row(e.ticker)
        shown, used = plan.shown_weights[k], plan.weights[k]
        kinds.add(e.kind)
        assert shown == e.old_weight and used == e.new_weight
        if e.kind == SPLIT:
            assert used == shown * e.ratio and e.ratio in (2, 3)
        elif e.kind == REVERSE:
            assert used * e.ratio == shown and e.ratio in (2, 3)
        else:
            assert used != shown and used >= HARD.min_weight
        others = [j for j in range(len(plan.tickers)) if j != k]
        assert all(plan.weights[j] == plan.shown_weights[j] for j in others)  # nothing else changes
        assert plan.nav == nav(plan.weights, plan.prices, plan.tick)
        assert plan.naive_nav == nav(plan.shown_weights, plan.prices, plan.tick) != plan.nav
    assert kinds == {SPLIT, REVERSE, REBAL}


def test_split_price_is_post_split():
    cfg = HARD.replace(price_places=2)
    for m, i, plan in event_rounds(cfg, range(200)):
        e = plan.event
        if e.kind != SPLIT:
            continue
        k = plan.row(e.ticker)
        prev = plan.prev_prices[k]
        assert plan.prices[k] < prev * D("0.6")  # roughly prev / N after a ±few % move
        break


def test_event_weights_carry_into_later_rounds():
    checked = 0
    for m, i, plan in event_rounds():
        if i + 1 < len(m.rounds):
            nxt = m.rounds[i + 1]
            assert nxt.shown_weights == plan.weights  # the table now shows the adjusted weight
            if nxt.event is None:
                assert nxt.weights == plan.weights and nxt.nav == nav(plan.weights, nxt.prices, nxt.tick)
            checked += 1
    assert checked > 50


def test_value_continuity_through_a_split():
    """A split changes price and weight together, so W × P barely moves (just the round's price move)."""
    for m, i, plan in event_rounds(HARD, range(300)):
        e = plan.event
        if e.kind in (SPLIT, REVERSE):
            k = plan.row(e.ticker)
            before = plan.shown_weights[k] * plan.prev_prices[k]
            after = plan.weights[k] * plan.prices[k]
            assert abs(after - before) / before < D("0.05")


# ── config ───────────────────────────────────────────────────────────────────


def test_presets_match_table():
    assert (EASY.stocks, EASY.weight_places, EASY.price_places) == (4, 1, 0)  # whole-dollar prices
    assert (MEDIUM.stocks, MEDIUM.weight_places, MEDIUM.price_places) == (5, 2, 1)  # tenths
    assert (HARD.stocks, HARD.weight_places, HARD.price_places) == (6, 2, 2)
    assert not any(hasattr(p, "show_wxp") for p in PRESETS.values())  # W × P is always shown
    assert [(p.rounds, p.timer_s, p.size) for p in (EASY, MEDIUM, HARD)] == [(6, 25, 40), (6, 20, 30), (8, 10, 20)]
    assert [(p.trader_sd, p.decide_min, p.decide_max) for p in (EASY, MEDIUM, HARD)] == [
        (D("1.00"), 11, 20), (D("0.30"), 7, 14), (D("0.10"), 2, 7)]
    assert (EASY.events, MEDIUM.events, HARD.events) == (False, False, True) and HARD.event_freq == 1 / 3
    assert [(p.skip_chance, p.gap_min, p.gap_max) for p in (EASY, MEDIUM, HARD)] == [
        (0.15, D("1.20"), D("3.50")), (0.22, D("0.70"), D("3.00")), (0.25, D("0.55"), D("3.00"))]
    assert all((p.fee, p.bonus, p.max_units) == (D(10), D("0.20"), 20) for p in PRESETS.values())
    assert all(not p.errors() for p in PRESETS.values())


@pytest.mark.parametrize(
    "changes",
    [dict(stocks=1), dict(stocks=11), dict(weight_places=3), dict(price_places=3), dict(price_places=-1), dict(timer_s=2),
     dict(size=0), dict(decide_min=9, decide_max=8), dict(event_freq=0), dict(trap_skill=1.5),
     dict(fee=D(-1)), dict(bonus=D("1.5")), dict(max_units=0), dict(seed="x"), dict(skip_chance=1.5),
     dict(gap_min=D("0.40")), dict(gap_min=D("3.00"), gap_max=D("2.00")), dict(gap_max=D("2.005"))],
)
def test_bad_configs_rejected(changes):
    assert EASY.replace(**changes).errors()


def test_config_round_trip():
    assert EtfConfig.from_dict(HARD.to_dict()) == HARD
