"""ETF Arb stage 2: the round state machine — P&L, fee, first-trade bonus, shared size, right call,
the timer. Computer traders here are idle (the stage-2 base trader) or driven by hand."""

from decimal import Decimal

import pytest

from mtt_games.games.etf.config import EASY, HARD
from mtt_games.games.etf.engine import OPEN, RECAP, RESULT, TIMEOUT, YOU, EtfGame, Round, ticks
from mtt_games.games.etf.model import BUY, SELL, SKIP, RoundPlan, bonus, gross, right_call
from mtt_games.games.etf.traders import Trader

D = Decimal
KESTREL, OSPREY, MERLIN = 1, 2, 3


class Idle(Trader):
    """Never decides in time, so it always skips."""

    def decide_at(self, number):
        return 10**9


def idle(game, seat, rng):
    return Idle(game, seat, rng)


def game_with(nav_value: str, bid: str, size: int = 40, cfg=EASY) -> EtfGame:
    """A game whose current round is a one-stock basket with NAV = nav_value and the quote bid @ bid + 0.20."""
    g = EtfGame(cfg.replace(seed=1, size=size), traders=idle)
    plan = RoundPlan(1, ("AAPL",), (D(nav_value),), (D(nav_value),), (D(1),), (D(1),), None, D(0), D(bid),
                     D(bid) + D("0.20"))
    g.rounds[-1] = Round.open(plan, g.now, size)
    return g


# ── P&L ──────────────────────────────────────────────────────────────────────


def test_howto_example():
    """NAV 237.50, buy 10 @ 233.40: gross 41.00, fee 10, first-trade bonus 20% of 31.00 = 6.20 → +37.20."""
    g = game_with("237.50", "233.20")  # ask 233.40
    fill = g.buy(10)
    assert (fill.price, fill.gross, fill.fee, fill.bonus, fill.net) == (
        D("233.40"), D("41.00"), D(10), D("6.20"), D("37.20"))
    assert fill.first and isinstance(fill.net, Decimal)


def test_same_trade_not_first_gets_no_bonus():
    g = game_with("237.50", "233.20")
    g.trade(KESTREL, BUY, 5)
    fill = g.buy(10)
    assert not fill.first and fill.bonus == 0 and fill.net == D("31.00")


def test_sell_gross_and_negative_first_trade_gets_no_bonus():
    g = game_with("100.00", "100.50")  # bid above NAV: selling earns 0.50/unit
    fill = g.sell(10)
    assert (fill.gross, fill.net) == (D("5.00"), D("-5.00"))  # 5 − 10 fee; negative, so no bonus
    assert fill.first and fill.bonus == 0
    assert gross(BUY, 3, D("100"), D("100.50"), D("100.70")) == D("-2.10")
    assert bonus(True, D("10.00"), D(10), D("0.20")) == 0  # exactly zero: not positive
    assert bonus(True, D("10.01"), D(10), D("0.20")) == D("0.002")
    assert bonus(False, D("50"), D(10), D("0.20")) == 0


def test_bonus_goes_to_the_first_trade_by_anyone():
    g = game_with("237.50", "233.20")
    first = g.trade(OSPREY, BUY, 20)
    assert first.first and first.bonus == D("0.20") * (D("82.00") - 10)
    assert not g.buy(5).first


# ── shared size ──────────────────────────────────────────────────────────────


def test_size_depletes_across_traders_and_caps_units():
    g = game_with("237.50", "233.20", size=40)
    g.trade(KESTREL, BUY, 20)
    g.trade(OSPREY, BUY, 15)
    assert (g.round.ask_left, g.round.bid_left) == (5, 40)
    with pytest.raises(ValueError, match="1–5"):
        g.buy(6)
    g.buy(5)
    assert g.round.ask_left == 0
    assert [f.units for f in g.round.fills] == [20, 15, 5]


def test_empty_side_is_disabled():
    g = game_with("237.50", "233.20", size=20)
    g.trade(KESTREL, BUY, 20)
    assert not g.can_trade(YOU, BUY) and g.can_trade(YOU, SELL)
    with pytest.raises(ValueError, match="nothing left at the ask"):
        g.buy(1)
    with pytest.raises(ValueError, match="nothing left"):
        g.trade(MERLIN, BUY, 1)


def test_units_capped_at_max_units():
    g = game_with("237.50", "233.20", size=40)
    with pytest.raises(ValueError, match="1–20"):
        g.buy(21)
    with pytest.raises(ValueError):
        g.buy(0)


def test_one_trade_per_player_per_round():
    g = game_with("237.50", "233.20")
    g.trade(KESTREL, BUY, 1)
    with pytest.raises(RuntimeError, match="already acted"):
        g.trade(KESTREL, SELL, 1)


# ── right call ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "nav,bid,units,call",
    [
        ("100.80", "100.00", 20, BUY),  # (100.80 − 100.20) × 20 = 12 > 10
        ("100.70", "100.00", 20, SKIP),  # 0.50 × 20 = 10: not over the fee
        ("100.71", "100.00", 20, BUY),  # 0.51 × 20 = 10.20
        ("99.40", "100.00", 20, SELL),  # 0.60 × 20 = 12
        ("99.50", "100.00", 20, SKIP),  # 0.50 × 20 = 10
        ("100.80", "100.00", 10, SKIP),  # size-limited: 0.60 × 10 = 6
        ("101.30", "100.00", 10, BUY),  # 1.10 × 10 = 11
    ],
)
def test_right_call(nav, bid, units, call):
    assert right_call(D(nav), D(bid), D(bid) + D("0.20"), units, D(10))[0] == call


def test_right_units_use_size_at_round_start():
    assert game_with("100", "99", size=40).right_units() == 20
    small = game_with("100.80", "100.00", size=10)
    assert small.right_units() == 10 and small.right_call()[0] == SKIP  # 0.60 × 10 = 6 ≤ 10


# ── timer + flow ─────────────────────────────────────────────────────────────


def test_timeout_at_the_timer():
    g = EtfGame(EASY.replace(seed=2), traders=idle)
    g.advance(ticks(EASY.timer_s) - 1)
    assert g.phase == OPEN and g.seconds_left() == 0.25
    g.advance()
    assert g.phase == RESULT and g.round.decisions[YOU].action == TIMEOUT
    assert all(g.round.decisions[s].action == SKIP for s in (1, 2, 3))


def test_round_ends_when_everyone_has_decided():
    g = EtfGame(EASY.replace(seed=2), traders=idle)  # idle traders never decide in time
    g.advance(8)
    g.skip()
    assert g.phase == RESULT and g.round.decisions[YOU].t == 8


def test_session_runs_to_recap_and_totals_add_up():
    g = EtfGame(HARD.replace(seed=3), traders=idle)
    for n in range(HARD.rounds):
        side = BUY if g.right_call()[0] == BUY else SELL
        g.trade(YOU, side, 7)
        assert g.phase == RESULT
        g.next_round()
    assert g.phase == RECAP and len(g.rounds) == HARD.rounds
    assert g.total(YOU) == sum(r.decisions[YOU].net for r in g.rounds)
    assert all(isinstance(r.decisions[YOU].net, Decimal) for r in g.rounds)
    with pytest.raises(RuntimeError):
        g.next_round()
