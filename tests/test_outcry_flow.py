"""Outcry stage 3: commands, the tick clock and the round flow (forced open, forced response, outcry,
reveals, report), anonymity, and zero-sum. Computer traders here are the rule-following base trader
or scripted spies; their outcry styles are tested in test_outcry_traders.py."""

import dataclasses
import random

import pytest

from mtt_games.games.outcry.book import BID, OFFER
from mtt_games.games.outcry.commands import BOTH, CommandError, parse_command
from mtt_games.games.outcry.config import EASY, HARD, MEDIUM
from mtt_games.games.outcry.engine import (
    CLOSED,
    OPEN,
    OUTCRY_KIND,
    OUTCRY,
    REPORT,
    RESPOND,
    RESULTS,
    YOU,
    OutcryGame,
    PublicReveal,
    PublicState,
    Trade,
    ticks,
    trade_score,
)
from mtt_games.games.outcry.traders import BUY, PASS, SELL, Trader

# ── helpers ──────────────────────────────────────────────────────────────────


def seed_where(pred, preset=EASY, limit=500):
    return next(s for s in range(limit) if pred(OutcryGame(preset.replace(seed=s))))


def finish_outcry(game: OutcryGame) -> None:
    game.advance_to(game.round.outcry_end)
    assert game.phase == CLOSED


def play(game: OutcryGame, rng: random.Random, commands: bool = True) -> OutcryGame:
    """Random but legal player: opens near fair, responds at random, fires random commands mid-outcry."""
    while game.phase != RESULTS:
        if game.phase == OPEN:
            mid = round(game.fair(YOU))
            w = rng.randint(1, 30)
            game.player_open(mid - w // 2, mid - w // 2 + w)
        elif game.phase == RESPOND:
            game.player_respond(rng.choice([BUY, SELL, PASS]))
        elif game.phase == OUTCRY:
            if commands:
                for _ in range(rng.randint(0, 4)):
                    game.advance(rng.randint(0, 20))
                    if game.phase != OUTCRY:
                        break
                    p = round(game.fair(YOU)) + rng.randint(-15, 15)
                    game.command(rng.choice([f"b {p}", f"o {p}", f"{p} @ {p + 3}", "buy", "sell", "x", "xb"]))
            if game.phase == OUTCRY:
                finish_outcry(game)
        elif game.phase == CLOSED:
            game.next_round()
        elif game.phase == REPORT:
            game.report(game.score(YOU))
    return game


# ── commands ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,kind,bid,ask",
    [("b 464", "bid", 464, None), ("B464", "bid", 464, None), ("o 467", "offer", None, 467),
     ("464 @ 467", BOTH, 464, 467), ("464@467", BOTH, 464, 467), ("  buy ", "buy", None, None),
     ("SELL", "sell", None, None), ("x", "x", None, None), ("xb", "xb", None, None), ("xo", "xo", None, None)],
)
def test_parse_valid_commands(text, kind, bid, ask):
    cmd = parse_command(text)
    assert (cmd.kind, cmd.bid, cmd.ask) == (kind, bid, ask)


@pytest.mark.parametrize("text", ["", "b", "b abc", "o -4", "467 @ 464", "5 @ 5", "lift", "b 4.5", "x 4", "99999 @ 100000"])
def test_parse_rejects_bad_input(text):
    with pytest.raises(CommandError):
        parse_command(text)


# ── forced open ──────────────────────────────────────────────────────────────


def test_trader_opener_quotes_are_valid():
    for seed in range(40):
        g = OutcryGame(MEDIUM.replace(seed=seed))
        if g.round.opener != YOU:
            assert g.phase == RESPOND
            assert 0 <= g.round.bid < g.round.ask <= 800


def your_open() -> OutcryGame:
    g = OutcryGame(EASY.replace(seed=seed_where(lambda g: g.round.opener == YOU)))
    assert g.phase == OPEN
    return g


def test_player_open_validation_has_no_width_cap():
    g = your_open()
    assert g.max_price == 800
    assert g.open_errors(0, 800) == []  # as wide as it gets
    assert g.open_errors(400, 401) == []  # 1 wide
    assert g.open_errors(400, 400) == ["ask must be above bid"]
    assert g.open_errors(410, 400) == ["ask must be above bid"]
    assert g.open_errors(-1, 400) == ["bid can't be negative"]
    assert g.open_errors(400, 801) == ["ask can't be above 800"]
    assert g.open_errors(390.5, 410) == ["bid and ask must be whole numbers"]
    for bid, ask in ((410, 400), (-1, 400), (400, 801)):
        with pytest.raises(ValueError):
            g.player_open(bid, ask)
    assert g.phase == OPEN


@pytest.mark.parametrize("bid,ask", [(0, 800), (400, 401)])
def test_very_wide_and_one_wide_opens_are_accepted(bid, ask):
    g = your_open()
    g.player_open(bid, ask)
    assert g.phase == OUTCRY and (g.round.bid, g.round.ask) == (bid, ask)
    assert len(g.round.responses) == EASY.players - 1  # everyone else answered


def test_open_timeout_auto_quotes_400_without_outcry_history():
    g = OutcryGame(EASY.replace(seed=seed_where(lambda g: g.round.opener == YOU)))
    g.advance(ticks(EASY.respond_s) - 1)
    assert g.phase == OPEN
    g.advance()
    assert g.round.auto_quoted and (g.round.bid, g.round.ask) == (395, 405)
    assert any("auto-quoted 395 @ 405 (no outcry quotes yet ± 5)" in line for line in g.log)


def test_open_timeout_uses_your_last_outcry_mid():
    def opens_later(g):
        return YOU in g.setup.openers[1:] and g.setup.openers[0] != YOU

    g = OutcryGame(EASY.replace(seed=seed_where(opens_later)))
    target = g.setup.openers.index(YOU, 1) + 1
    g.player_respond(PASS)
    g.command("420 @ 430")
    while len(g.rounds) < target:
        if g.phase == OUTCRY:
            finish_outcry(g)
        elif g.phase == CLOSED:
            g.next_round()
        elif g.phase == RESPOND:
            g.player_respond(PASS)
    assert g.phase == OPEN
    g.advance(ticks(EASY.respond_s))
    assert (g.round.bid, g.round.ask) == (420, 430)  # mid 425 ± 5
    assert any("auto-quoted 420 @ 430 (your last outcry mid ± 5)" in line for line in g.log)


# ── forced response ──────────────────────────────────────────────────────────


class Spy(Trader):
    """Records what it could see when asked to respond, and always buys."""

    seen: list = []

    def respond(self, bid, ask):
        g = self.game
        Spy.seen.append((len(g.trades), len(g.round.responses), g.public().responses, g.your_response))
        return BUY


def spy_factory(game, seat, style, rng):
    return Spy(game, seat, rng)


def test_forced_responses_are_blind_and_simultaneous():
    Spy.seen = []
    seed = seed_where(lambda g: g.round.opener != YOU)
    g = OutcryGame(EASY.replace(seed=seed), traders=spy_factory)
    g.player_respond(SELL)
    decided = Spy.seen
    assert len(decided) == EASY.players - 2  # every trader but the opener
    assert all(seen[:3] == (0, 0, ()) for seen in decided)  # no response had been applied or shown yet
    r = g.round
    order = [s for s in g.setup.response_orders[0] if s != r.opener]
    assert [x.seat for x in r.responses] == order  # applied in the pre-drawn random order
    assert {x.action for x in r.responses if x.seat != YOU} == {BUY}
    assert g.public().responses  # shown all at once, after they were applied


def test_trader_responses_ignore_yours():
    """Blind: the same seed with a different answer from you gives identical computer responses."""
    seed = seed_where(lambda g: g.round.opener != YOU)
    answers = []
    for mine in (BUY, SELL, PASS):
        g = OutcryGame(EASY.replace(seed=seed))
        g.player_respond(mine)
        answers.append({x.seat: x.action for x in g.round.responses if x.seat != YOU})
    assert answers[0] == answers[1] == answers[2]


def test_limit_capped_responses_are_skipped_and_logged():
    Spy.seen = []
    seed = seed_where(lambda g: g.round.opener != YOU)
    g = OutcryGame(EASY.replace(seed=seed), traders=spy_factory)
    opener = g.round.opener
    g.positions[opener] = -EASY.limit + 2  # the opener can only sell 2 more
    g.player_respond(PASS)
    applied = [x for x in g.round.responses if x.action == BUY and x.applied]
    skipped = [x for x in g.round.responses if x.action == BUY and not x.applied]
    assert len(applied) == 2 and len(skipped) == EASY.players - 4
    assert all(f"{g.names[opener]} at the ±10 limit" in x.note for x in skipped)
    assert sum(1 for line in g.log if "skipped" in line) == len(skipped)
    assert g.positions[opener] == -EASY.limit


def test_player_timeout_is_a_pass():
    g = OutcryGame(EASY.replace(seed=seed_where(lambda g: g.round.opener != YOU)))
    g.advance(ticks(EASY.respond_s))
    mine = next(x for x in g.round.responses if x.seat == YOU)
    assert mine.action == "timeout" and g.phase == OUTCRY and g.positions[YOU] == 0


# ── outcry + clock ───────────────────────────────────────────────────────────


def to_outcry(preset=EASY, seed=1) -> OutcryGame:
    g = OutcryGame(preset.replace(seed=seed))
    if g.phase == OPEN:
        g.player_open(395, 405)
    else:
        g.player_respond(PASS)
    assert g.phase == OUTCRY and g.public().phase == "outcry"
    return g


def test_outcry_runs_exactly_its_duration_on_the_tick_clock():
    g = to_outcry()
    start = g.now
    assert g.seconds_left() == EASY.outcry_s
    g.advance(ticks(EASY.outcry_s) - 1)
    assert g.phase == OUTCRY and g.seconds_left() == 0.25
    g.advance()
    assert g.phase == CLOSED and g.now == start + ticks(EASY.outcry_s)


def test_commands_echo_and_bad_input_is_never_sent():
    g = to_outcry()
    assert g.command("b 380")[0].text == "✓ bid 380 posted"
    assert g.command("o 420")[0].text == "✓ offer 420 posted"
    before = (list(g.book.bids), list(g.book.offers))
    echo = g.command("o banana")[0]
    assert not echo.ok and echo.text.startswith("✗") and (g.book.bids, g.book.offers) == before
    assert g.command("b 381")[0].ok and g.you().bid == 381  # replaces
    assert g.command("xb")[0].text == "✓ cancelled your bid" and g.you().bid is None
    assert g.command("x")[0].text == "✓ cancelled all orders" and g.you().offer is None
    assert g.command("x")[0].text == "✓ nothing to cancel (all orders)"
    assert g.command("buy")[0].text == "✗ no offer to lift"
    g.place(1, OFFER, 402)
    echo = g.command("buy")[0]
    assert echo.ok and echo.text == f"✓ bought 1 @ 402 from {g.names[1]}" and g.positions[YOU] == 1
    g.place(2, BID, 399)
    assert g.command("sell")[0].text == f"✓ sold 1 @ 399 to {g.names[2]}"
    g.place(3, OFFER, 401)
    lines = g.command("401 @ 405")
    assert lines[0].text == f"✓ bid 401 → bought 1 @ 401 from {g.names[3]}" and lines[1].text == "✓ offer 405 posted"


def test_orders_are_wiped_at_the_close():
    g = to_outcry()
    g.command("380 @ 420")
    g.place(4, BID, 300)
    finish_outcry(g)
    assert not g.book.bids and not g.book.offers


def test_rounds_reveals_and_report():
    g = to_outcry(seed=5)
    for r in range(1, EASY.rounds + 1):
        if g.phase in (OPEN, RESPOND):
            g.player_respond(PASS) if g.phase == RESPOND else g.player_open(395, 405)
        finish_outcry(g)
        assert g.revealed == r and len(g.public().reveals) == r
        g.next_round()
    assert g.phase == REPORT and len(g.public().reveals) == EASY.players
    assert sum(x.value for x in g.public().reveals) == g.settle
    g.advance(4)
    assert g.report(g.score(YOU)) is True and g.report_correct and g.report_seconds == 1.0 and g.phase == RESULTS


def test_report_wrong_and_timeout_wrong():
    g = play(OutcryGame(EASY.replace(seed=3)), random.Random(3))
    assert g.report_correct
    g2 = OutcryGame(EASY.replace(seed=3))
    rng = random.Random(3)
    while g2.phase != REPORT:
        play_step(g2, rng)
    assert g2.report(g2.score(YOU) + 1) is False and not g2.report_correct
    g3 = OutcryGame(EASY.replace(seed=3))
    while g3.phase != REPORT:
        play_step(g3, random.Random(1))
    g3.advance(ticks(EASY.report_s))
    assert g3.phase == RESULTS and g3.reported is None and not g3.report_correct


def play_step(g, rng):
    if g.phase == OPEN:
        g.player_open(395, 405)
    elif g.phase == RESPOND:
        g.player_respond(PASS)
    elif g.phase == OUTCRY:
        finish_outcry(g)
    elif g.phase == CLOSED:
        g.next_round()


# ── anonymity ────────────────────────────────────────────────────────────────


def test_public_state_has_no_owners():
    assert {f.name for f in dataclasses.fields(PublicReveal)} == {"value", "label"}
    assert not any("owner" in f.name or "seat" in f.name or "mine" in f.name for f in dataclasses.fields(PublicState))
    g = OutcryGame(EASY.replace(seed=11))
    rng = random.Random(0)
    while g.phase != REPORT:
        play_step(g, rng)
        for r in g.public().reveals:
            assert isinstance(r, PublicReveal)
        with pytest.raises(RuntimeError):
            g.results()
    g.report(0)
    res = g.results()
    assert sorted(row.number for row in res.leaderboard) == sorted(g.setup.numbers)


def test_your_own_reveal_is_flagged_only_for_you():
    seed = seed_where(lambda g: g.setup.reveal_order[0] == YOU)
    g = OutcryGame(EASY.replace(seed=seed))
    play_step(g, None)
    finish_outcry(g)
    assert g.you().reveals[0].mine is True
    assert g.public().reveals[0] == PublicReveal(g.setup.numbers[YOU], g.setup.reveal_labels[0])
    for seat in range(1, EASY.players):
        assert g.knowledge(seat).reveals[0].mine is False


# ── zero-sum + determinism ───────────────────────────────────────────────────


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_zero_sum_with_base_traders(preset):
    for seed in range(8):
        g = play(OutcryGame(preset.replace(seed=seed)), random.Random(seed))
        assert sum(g.pnl(s) for s in range(preset.players)) == 0
        assert sum(g.positions) == 0 and all(abs(p) <= preset.limit for p in g.positions)


def test_opening_width_stat():
    for seed in range(12):
        g = play(OutcryGame(EASY.replace(seed=seed)), random.Random(seed))
        res = g.results()
        mine = [r.ask - r.bid for r in g.rounds if r.opener == YOU]
        theirs = [r.ask - r.bid for r in g.rounds if r.opener != YOU]
        assert res.your_open_width == (sum(mine) / len(mine) if mine else None)
        assert res.computer_open_width == (sum(theirs) / len(theirs) if theirs else None)
    never = next(s for s in range(200) if YOU not in OutcryGame(EASY.replace(seed=s)).setup.openers)
    assert play(OutcryGame(EASY.replace(seed=never)), random.Random(0)).results().your_open_width is None


def test_results_metrics():
    g = play(OutcryGame(EASY.replace(seed=4)), random.Random(4))
    res = g.results()
    assert sum(row.pnl for row in res.leaderboard) == 0
    assert [row.rank for row in res.leaderboard] == sorted(row.rank for row in res.leaderboard)
    assert res.true_range == (g.setup.low, g.setup.high) and res.settle == g.settle
    assert res.responses_traded + res.responses_passed == EASY.rounds - res.opens
    assert [r for r, _ in res.last_prices] == list(range(1, EASY.rounds + 1))
    if res.your_trades:
        assert res.best.edge_settle >= res.worst.edge_settle
        assert sum(y.edge_settle for y in res.your_trades) == pytest.approx(res.pnl)


# ── pace cap ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_pace_cap_holds_over_a_full_outcry(preset):
    """Driven by the tick clock alone: computer actions are never closer together than the pace cap."""
    gap = ticks(preset.pace_s)
    for seed in range(4):
        g = to_outcry(preset, seed)
        start = len(g.computer_actions)
        finish_outcry(g)
        actions = g.computer_actions[start:]
        assert actions, "the traders should do something in a whole outcry"
        assert all(b[0] - a[0] >= gap for a, b in zip(actions, actions[1:]))
        assert len({t for t, _ in actions}) == len(actions)  # never two in one tick


def test_waiting_traders_rotate_who_goes_first():
    g = to_outcry(HARD, 1)
    finish_outcry(g)
    assert len({seat for _, seat in g.computer_actions}) >= 4  # turns are shared, not hogged by seat 1


def test_the_player_bypasses_the_cap():
    g = to_outcry(EASY, 1)
    while g.pace_free_at <= g.now:  # step until a computer has just acted and the cap is blocking them
        g.advance()
    assert g.phase == OUTCRY
    blocked_until = g.pace_free_at
    echoes = [g.command(c)[0] for c in ("b 10", "b 11", "o 9000", "xb", "o 8999")]
    assert all(e.ok for e in echoes)  # five actions in one capped tick, none refused or delayed
    assert g.you().offer == 8999 and g.you().bid is None
    assert g.pace_free_at == blocked_until  # and they don't use up the computers' slot


# ── trade score ──────────────────────────────────────────────────────────────


def test_trade_score_rule():
    assert trade_score(True, 395, 400) == 1  # bought below the settle
    assert trade_score(True, 405, 400) == -1
    assert trade_score(False, 405, 400) == 1  # sold above
    assert trade_score(False, 395, 400) == -1
    assert trade_score(True, 400, 400) == 0 and trade_score(False, 400, 400) == 0  # exactly at the settle


def scored_game(prices_and_sides, size=1):
    """A finished game whose trades for you are replaced by the given (buying, price) list."""
    g = OutcryGame(EASY.replace(seed=3, trade_size=size))
    rng = random.Random(0)
    while g.phase != REPORT:
        play_step(g, rng)
    settle = g.settle
    g.trades = [Trade(1, OUTCRY_KIND, 0, YOU if buy else 1, 1 if buy else YOU, settle + d, size, YOU)
                for buy, d in prices_and_sides]
    return g


def test_net_score_counts_wins_losses_and_at_settle_trades():
    # buy 3 below (+1), buy 2 above (−1), sell 5 above (+1), sell at the settle (0), sell 1 below (−1), buy 7 below (+1)
    g = scored_game([(True, -3), (True, 2), (False, 5), (False, 0), (False, -1), (True, -7)], size=4)
    assert g.score(YOU) == 1
    assert g.report("1") is True and g.report_correct
    res = g.results()
    assert [y.score for y in res.your_trades] == [1, -1, 1, 0, -1, 1]
    assert res.score == 1


def test_negative_score_reports_are_accepted():
    g = scored_game([(True, 4), (False, -2), (True, 0)])  # −1, −1, 0
    assert g.score(YOU) == -2
    assert g.report("-2") is True and g.report_correct and g.reported == -2


def test_wrong_score_and_timeout_are_wrong():
    g = scored_game([(True, -3)])
    assert g.report(0) is False and not g.report_correct
    g = scored_game([(True, -3)])
    g.advance(ticks(EASY.report_s))
    assert g.phase == RESULTS and g.reported is None and not g.report_correct


def test_leaderboard_keeps_dollar_pnl():
    for seed in range(6):
        g = play(OutcryGame(EASY.replace(seed=seed)), random.Random(seed))
        board = {row.name: row.pnl for row in g.results().leaderboard}
        for seat, name in enumerate(g.names):
            assert board[name] == g.cash[seat] + g.positions[seat] * g.settle
        assert sum(board.values()) == 0
