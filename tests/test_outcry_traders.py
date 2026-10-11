"""Outcry stage 4: computer trader styles, learning from the tape, zero-sum with real traders."""

import random

import pytest

from met_games.games.outcry.book import BID, OFFER
from met_games.games.outcry.config import ANCHOR, CHASER, EASY, HARD, MAKER, MEDIUM, PASSIVE, SNIPER
from met_games.games.outcry.engine import CLOSED, OPEN, OUTCRY, REPORT, RESPOND, RESULTS, YOU, OutcryGame, Trade
from met_games.games.outcry.traders import (
    BUY,
    OPEN_WIDTHS,
    PASS,
    SELL,
    AnchorTrader,
    ChaserTrader,
    MakerTrader,
    PassiveTrader,
    SniperTrader,
    anchor_estimate,
    chase,
    needs_requote,
    quote_around,
    respond_rule,
    take_decision,
)

# ── pure rules at their boundaries ──────────────────────────────────────────


@pytest.mark.parametrize(
    "est,expected",
    [(406.0, BUY), (405.99, PASS), (394.0, SELL), (394.01, PASS), (400.0, PASS)],
)
def test_responder_rule_boundaries(est, expected):
    assert respond_rule(est, 395, 405) == expected  # buy if est ≥ ask + 1, sell if est ≤ bid − 1


@pytest.mark.parametrize(
    "est,bid,offer,edge,expected",
    [
        (402.0, 390, 400, 2, BID),  # offer exactly 2 below the estimate: lift
        (401.9, 390, 400, 2, None),
        (398.0, 400, 410, 2, OFFER),  # bid exactly 2 above: hit
        (398.1, 400, 410, 2, None),
        (400.0, None, None, 2, None),
        (405.0, 395, 400, 5, BID),  # PASSIVE's edge
        (404.9, 395, 400, 5, None),
        (401.0, 390, 400, 1, BID),  # CHASER / ANCHOR edge
        (400.0, 403, 395, 2, BID),  # both qualify: lifting 395 (+5) beats hitting 403 (+3)
    ],
)
def test_take_decision_boundaries(est, bid, offer, edge, expected):
    assert take_decision(est, bid, offer, edge) == expected


def test_take_decision_tie_lifts():
    assert take_decision(400.0, 403, 397, 2) == BID


def test_requote_rule():
    assert needs_requote(True, True, False, 400, 400.4) is False  # nothing changed: idle
    assert needs_requote(True, True, False, 400, 400.6) is True  # estimate moved
    assert needs_requote(True, False, False, 400, 400.0) is True  # a side is missing
    assert needs_requote(True, True, True, 400, 400.0) is True  # traded since the last quote
    assert needs_requote(False, False, False, None, 400.0) is True


def test_anchor_estimate_is_naive():
    assert anchor_estimate([40], 8) == 320
    assert anchor_estimate([40, 60, 20], 8) == 320  # 8 × mean, whatever the labels or range say


def test_chaser_moves_half_way_to_the_last_trade():
    assert chase(400.0, 420) == 410.0
    assert chase(400.0, None) == 400.0


def test_quote_around():
    assert quote_around(400.0, 6) == (397, 403)
    assert quote_around(400.0, 5) == (398, 403)  # 397.5 rounds half to even
    assert quote_around(400.4, 3) == (399, 402)


# ── styles inside a game ─────────────────────────────────────────────────────


def styled(style_cls, preset=EASY, seed=1):
    """A game whose every trader has one style; returns it already in the outcry."""
    def factory(game, seat, style, rng):
        return style_cls(game, seat, rng)

    g = OutcryGame(preset.replace(seed=seed), traders=factory)
    if g.phase == OPEN:
        g.player_open(1, 2)  # far from fair: responders trade, but that's fine for these tests
    else:
        g.player_respond(PASS)
    assert g.phase == OUTCRY
    g.book.clear()
    return g


def test_maker_quotes_width_3_to_6_around_its_estimate_and_idles_when_nothing_changed():
    g = styled(MakerTrader)
    t = g.traders[1]
    widths = set()
    for _ in range(40):
        g.cancel(1)
        t.quoted_mid = None
        t.act()
        b, o = g.book.order_of(1, BID), g.book.order_of(1, OFFER)
        widths.add(o.price - b.price)
        assert abs((b.price + o.price) / 2 - t.estimate()) <= 0.5 + 0.01
    assert widths == {3, 4, 5, 6}
    before = (g.book.order_of(1, BID), g.book.order_of(1, OFFER))
    t.act()
    assert (g.book.order_of(1, BID), g.book.order_of(1, OFFER)) == before  # idle


def test_maker_requotes_after_a_trade_and_when_its_estimate_moves():
    g = styled(MakerTrader)
    t = g.traders[1]
    t.act()
    first = g.book.order_of(1, OFFER)
    g.command(f"b {first.price}")  # you lift the maker's offer
    assert t.traded
    t.act()
    assert g.book.order_of(1, OFFER) is not None and not t.traded
    old = g.book.order_of(1, BID)
    t.offset += 5  # estimate moves
    t.act()
    assert g.book.order_of(1, BID).seq != old.seq


def test_sniper_takes_only_at_two_better():
    g = styled(SniperTrader)
    t = g.traders[1]
    est = t.estimate()
    g.place(YOU, OFFER, int(est) + 1)  # less than 2 better: idle
    t.act()
    assert not g.trades or g.trades[-1].buyer != 1
    g.cancel(YOU)
    import math

    g.place(YOU, OFFER, math.floor(est - 2))  # at least 2 better: lift
    t.act()
    assert g.trades[-1].buyer == 1 and g.trades[-1].seller == YOU
    assert g.book.order_of(1, BID) is None and g.book.order_of(1, OFFER) is None  # snipers never quote


def test_passive_quotes_wide_slowly_and_rarely_takes():
    g = styled(PassiveTrader)
    t = g.traders[1]
    widths = set()
    for _ in range(60):
        g.cancel(1)
        t.quoted_mid = None
        t.act()
        widths.add(g.book.order_of(1, OFFER).price - g.book.order_of(1, BID).price)
    assert widths == set(range(8, 15))
    lo, hi = EASY.cooldown
    cooldowns = [t.cooldown_ticks() * 0.25 for _ in range(200)]
    assert 2 * lo - 0.25 <= min(cooldowns) and max(cooldowns) <= 2 * hi + 0.25  # twice the preset's cooldown
    g.cancel(1)
    est = t.estimate()
    import math

    g.place(YOU, OFFER, math.floor(est - 4.5))  # < 5 better: no take, just quotes
    t.act()
    assert not any(tr.buyer == 1 and tr.seller == YOU for tr in g.trades if tr.kind == "outcry")


def test_chaser_uses_the_last_trade_price():
    g = styled(ChaserTrader)
    t = g.traders[1]
    g.last_price = None
    base = t.estimate()
    g.last_price = round(base) + 40
    assert t.estimate() == pytest.approx(base + 0.5 * (g.last_price - base))


def test_anchor_trader_uses_the_naive_estimate():
    g = styled(AnchorTrader)
    t = g.traders[2]
    assert t.estimate() == pytest.approx(EASY.players * sum(g.knowledge(2).known) / len(g.knowledge(2).known))


def test_cooldowns_follow_the_preset_speed():
    for preset in (EASY, MEDIUM, HARD):
        g = styled(MakerTrader, preset)
        lo, hi = preset.cooldown
        draws = [g.traders[1].cooldown_ticks() * 0.25 for _ in range(300)]
        assert lo - 0.25 <= min(draws) and max(draws) <= hi + 0.25


def test_computer_opener_widths_stay_in_their_style_ranges():
    seen = {style: set() for style in OPEN_WIDTHS}
    for preset in (EASY, MEDIUM, HARD):
        for seed in range(150):
            g = OutcryGame(preset.replace(seed=seed))
            if g.round.opener == YOU:
                continue
            trader = g.traders[g.round.opener]
            width = g.round.ask - g.round.bid
            lo, hi = OPEN_WIDTHS[trader.style]
            assert lo <= width <= hi, (trader.style, width)
            assert abs((g.round.ask + g.round.bid) / 2 - trader.estimate()) <= 0.5 + 1e-9  # mid = estimate
            seen[trader.style].add(width)
    assert all(seen.values())  # every style opened somewhere


def test_traders_never_breach_the_limit():
    for seed in range(6):
        g = play(OutcryGame(HARD.replace(seed=seed, limit=10)), random.Random(seed))
        assert all(abs(p) <= 10 for p in g.positions)


# ── learning from the tape ──────────────────────────────────────────────────


def test_learning_on_hard_only():
    trade = Trade(1, "outcry", 0, 1, 2, 500, 1, 1)
    for preset, learns in ((EASY, False), (MEDIUM, False), (HARD, True)):
        g = styled(MakerTrader, preset)
        t = g.traders[3]
        before, offset = t.estimate(), t.offset
        t.on_trade(trade)
        if learns:
            assert t.offset - offset == pytest.approx(0.25 * (500 - before))
            assert t.estimate() == pytest.approx(before + 0.25 * (500 - before))
        else:
            assert t.offset == offset == 0 and t.estimate() == before


def test_every_hard_trader_learns_from_every_trade():
    g = styled(MakerTrader, HARD)
    before = {s: (t.estimate(), t.offset) for s, t in g.traders.items()}
    g.place(1, OFFER, 450)
    g.command("buy")
    assert g.trades[-1].buyer == YOU
    price = g.trades[-1].price
    for s, t in g.traders.items():
        est, offset = before[s]
        assert t.offset - offset == pytest.approx(0.25 * (price - est))


# ── whole games ──────────────────────────────────────────────────────────────


def play(game, rng):
    while game.phase != RESULTS:
        if game.phase == OPEN:
            mid = round(game.fair(YOU))
            game.player_open(mid - 5, mid + 5)
        elif game.phase == RESPOND:
            game.player_respond(rng.choice([BUY, SELL, PASS]))
        elif game.phase == OUTCRY:
            for _ in range(rng.randint(0, 3)):
                game.advance(rng.randint(1, 30))
                if game.phase != OUTCRY:
                    break
                p = round(game.fair(YOU)) + rng.randint(-10, 10)
                game.command(rng.choice([f"b {p}", f"o {p}", "buy", "sell", "x"]))
            if game.phase == OUTCRY:
                game.advance_to(game.round.outcry_end)
        elif game.phase == CLOSED:
            game.next_round()
        elif game.phase == REPORT:
            game.report(game.score(YOU))
    return game


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_zero_sum_across_seeded_games(preset):
    for seed in range(10):
        g = play(OutcryGame(preset.replace(seed=seed)), random.Random(seed))
        pnls = [g.pnl(s) for s in range(preset.players)]
        assert sum(pnls) == 0 and sum(g.positions) == 0
        assert sum(r.pnl for r in g.results().leaderboard) == 0
        assert {s for s in g.setup.styles if s} <= {MAKER, SNIPER, PASSIVE, CHASER, ANCHOR}


def test_same_seed_and_same_inputs_replay_exactly():
    def trace(seed):
        g = play(OutcryGame(HARD.replace(seed=seed)), random.Random(99))
        return g.setup, g.trades, [g.pnl(s) for s in range(8)]

    assert trace(5) == trace(5)
    assert trace(5) != trace(6)


def test_computer_trades_depend_on_when_you_act():
    """Accepted and documented: with the same seed, when you act can change the computers' own trades."""
    def computer_trades(seed, delay):
        g = OutcryGame(EASY.replace(seed=seed))
        if g.phase == OPEN:
            g.player_open(395, 405)
        else:
            g.player_respond(PASS)
        g.advance(delay)
        g.command("buy")
        g.advance_to(g.round.outcry_end)
        return [t for t in g.trades if YOU not in (t.buyer, t.seller)]

    assert any(computer_trades(seed, 4) != computer_trades(seed, 80) for seed in range(5))
