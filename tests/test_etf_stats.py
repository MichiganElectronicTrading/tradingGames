"""ETF Arb recap: mistakes, tiles, size story, leaderboard."""

from decimal import Decimal

from mtt_games.games.etf.config import EASY
from mtt_games.games.etf.engine import RESULT, YOU, EtfGame, Round, ticks
from mtt_games.games.etf.model import BUY, SELL, Event, RoundPlan
from mtt_games.games.etf.stats import leaderboard, mistakes, size_story, tiles
from mtt_games.games.etf.traders import Trader

D = Decimal


class Idle(Trader):
    def decide_at(self, number):
        return 10**9


def session(rounds):
    """A game whose rounds are the given (nav, bid, event) one-stock plans, played by `act(game)` each."""
    g = EtfGame(EASY.replace(seed=1, rounds=len(rounds)), traders=lambda g, s, r: Idle(g, s, r))
    for i, (nav, bid, event, act) in enumerate(rounds, start=1):
        shown = event.old_weight if event else D(1)
        used = event.new_weight if event else D(1)
        price = D(nav) / used
        plan = RoundPlan(i, ("AAPL",), (price,), (price,), (shown,), (used,), event, D(0), D(bid), D(bid) + D("0.20"))
        g.rounds[-1] = Round.open(plan, g.now, EASY.size)
        act(g)
        if g.phase != RESULT:
            g.advance_to(g.round.start + ticks(EASY.timer_s))
        if i < len(rounds):
            g.next_round()
    return g


def test_every_mistake_type():
    split = Event("AAPL", "split", 2, D("0.5"), D("1.0"))  # table shows 0.5; NAV uses 1.0
    g = session([
        ("100.00", "101.00", None, lambda g: g.buy(10)),  # wrong direction: bought above NAV
        ("100.80", "100.00", None, lambda g: g.buy(5)),  # right side, too small: 0.60 × 5 − 10 < 0; 20 → +2
        ("100.20", "100.00", None, lambda g: g.buy(20)),  # skip round (gap 0.00) but traded
        ("103.00", "100.00", None, lambda g: g.skip()),  # skipped a trade round: BUY 20 → 2.80 × 20 − 10 = 46
        ("103.00", "100.00", split, lambda g: g.skip()),  # naive NAV 51.50 says SELL… skip ≠ naive; not a fall
        ("101.00", "100.00", Event("AAPL", "split", 2, D("0.5"), D("1.0")), lambda g: g.sell(20)),  # fell for it
    ])
    errs = mistakes(g)
    assert any(e.startswith("R1: wrong direction") for e in errs)
    assert any(e.startswith("R2: right side but too small") and "+$2.00" in e for e in errs)
    assert any(e.startswith("R3: traded on a skip round") for e in errs)
    assert any(e.startswith("R4: skipped a trade round") and "+$46.00" in e for e in errs)
    assert any(e.startswith("R6: fell for the event") for e in errs)
    assert not any(e.startswith("R5: fell") for e in errs)


def test_timeout_on_a_trade_round_is_a_mistake():
    g = session([("103.00", "100.00", None, lambda g: None)])
    assert any("timed out a trade round" in e for e in mistakes(g))


def test_tiles():
    g = session([
        ("103.00", "100.00", None, lambda g: g.buy(20)),  # right way, first
        ("97.00", "100.00", None, lambda g: g.buy(10)),  # wrong way
        ("100.10", "100.00", None, lambda g: g.skip()),  # skip round, skipped
        ("99.90", "100.00", None, lambda g: g.sell(1)),  # skip round (0.10 × 20 = 2), traded: right way, too small
    ])
    t = tiles(g)
    assert (t.right_trades, t.trades, t.right_skips, t.skip_rounds, t.first) == (2, 3, 1, 2, 3)
    assert t.avg_decision == 0.0


def test_size_story_and_leaderboard():
    g = EtfGame(EASY.replace(seed=1), traders=lambda g, s, r: Idle(g, s, r))
    g.trade(2, BUY, 20)
    g.trade(YOU, BUY, 15)
    assert size_story(g, g.round, BUY) == "ask 40 → 20 (OSPREY 20) → 5 (YOU 15)"
    assert size_story(g, g.round, SELL) == "bid 40 untouched"
    board = leaderboard(g)
    assert [name for _, name, _ in board][0] in ("OSPREY", "YOU", "KESTREL", "MERLIN")
    assert sum(total for _, _, total in board) == g.total(YOU) + g.total(2)
