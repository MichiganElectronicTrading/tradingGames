import pytest

from mtt_games.games.card.config import EASY, HARD, MEDIUM, CardConfig
from mtt_games.games.card.deck import Card
from mtt_games.games.card.engine import (
    BROKE,
    BUY,
    OUT_OF_RISK,
    PASS,
    SELL,
    TIMEOUT,
    CardSession,
    Decision,
    Market,
    Round,
    edge_per_unit,
    make_quote,
    risk_limits,
    trade_pnl,
)

# ── P&L and edge ─────────────────────────────────────────────────────────────


def test_pnl_long_short_pass():
    assert trade_pnl(BUY, 3, 20, 23, 30) == (30 - 23) * 3
    assert trade_pnl(BUY, 2, 20, 23, 15) == (15 - 23) * 2
    assert trade_pnl(SELL, 4, 20, 23, 15) == (20 - 15) * 4
    assert trade_pnl(SELL, 1, 20, 23, 31) == -11
    assert trade_pnl(PASS, 0, 20, 23, 31) == 0
    assert trade_pnl(TIMEOUT, 0, 20, 23, 31) == 0


def test_edge_per_unit():
    assert edge_per_unit(BUY, 25.5, 20, 23) == pytest.approx(2.5)
    assert edge_per_unit(SELL, 25.5, 20, 23) == pytest.approx(-5.5)
    with pytest.raises(ValueError):
        edge_per_unit(PASS, 25.5, 20, 23)


def test_quote_is_integer_two_way_around_noisy_mid():
    assert make_quote(24.0, 0.0, 4) == (22, 26)
    assert make_quote(24.0, 1.4, 3) == (24, 27)  # mid 25.4 → bid round(23.9)
    bid, ask = make_quote(17.3, -2.2, 2)
    assert (bid, ask) == (14, 16)


# ── risk limits ──────────────────────────────────────────────────────────────


def test_risk_limits_floor():
    # long worst = 30 - 10 = 20/unit → 500 // 20 = 25 ; short worst = 50 - 28 = 22 → 22
    assert risk_limits(500, 28, 30, 10, 50) == (25, 22)
    assert risk_limits(41, 28, 30, 10, 50) == (2, 1)


def test_risk_limits_cap_at_100():
    assert risk_limits(10_000, 28, 30, 10, 50) == (100, 100)


def test_riskless_side_is_capped_at_100():
    # ask below the minimum settle: buying cannot lose
    assert risk_limits(5, 8, 10, 10, 40) == (100, 0)
    # bid above the maximum settle: selling cannot lose
    assert risk_limits(5, 41, 44, 10, 40) == (0, 100)


def test_disabled_side_when_max_below_one():
    max_long, max_short = risk_limits(15, 28, 30, 10, 50)
    assert max_long == 0 and max_short == 0


def _round_with_decision(action, size, bid, ask, fair, settle_cards, max_long=10, max_short=10):
    market = Market(0, len(settle_cards), 0.0, 52, False, fair, 0, 0)
    rnd = Round(1, settle_cards, None, list(range(len(settle_cards))), None, 30, 500)
    rnd.tape.append((0.0, bid, ask))
    rnd.decision = Decision(action, size, 1.0, bid, ask, market, max_long, max_short)
    return rnd


@pytest.mark.parametrize(
    "action,size,fair,ranks,verdict",
    [
        (BUY, 1, 25.0, [14, 13], "good trade, good draw"),  # ask 22, settle 27
        (BUY, 1, 25.0, [2, 3], "good trade, bad draw"),
        (BUY, 1, 20.0, [14, 13], "bad trade, lucky"),
        (BUY, 1, 20.0, [2, 3], "bad trade, unlucky"),
        (PASS, 0, 20.5, [2, 3], "correct pass"),
        (PASS, 0, 24.0, [2, 3], "missed edge of 2.00/unit"),
        (TIMEOUT, 0, 24.0, [2, 3], "timed out"),
    ],
)
def test_verdicts(action, size, fair, ranks, verdict):
    rnd = _round_with_decision(action, size, 18, 22, fair, [Card(r, "♠") for r in ranks])
    assert rnd.verdict == verdict


def test_missed_edge_ignores_disabled_side():
    rnd = _round_with_decision(PASS, 0, 18, 22, 25.0, [Card(2, "♠")], max_long=0, max_short=10)
    assert rnd.decision.best_edge == pytest.approx(-7.0)
    assert rnd.verdict == "correct pass"


# ── session flow ─────────────────────────────────────────────────────────────


def test_session_trade_updates_balance_and_report():
    s = CardSession(EASY.replace(seed=11), mode="EASY")
    rnd = s.new_round()
    s.buy(1, 2.0)
    assert s.balance == 500 + rnd.pnl == rnd.balance_after
    assert rnd.pnl == rnd.settle - rnd.ask
    assert s.report(rnd.pnl, 3.0) is True
    with pytest.raises(RuntimeError):
        s.report(rnd.pnl, 3.0)


def test_report_never_changes_balance():
    s = CardSession(EASY.replace(seed=4))
    rnd = s.new_round()
    s.sell(1, 1.0)
    before = s.balance
    assert s.report(rnd.pnl + 1, 2.0) is False
    assert s.balance == before


def test_fixed_sizing_rejects_other_sizes():
    s = CardSession(EASY.replace(seed=1))
    s.new_round()
    with pytest.raises(ValueError):
        s.buy(2, 1.0)


def test_size_above_risk_limit_rejected():
    s = CardSession(MEDIUM.replace(seed=3, budget=60))
    rnd = s.new_round()
    max_long, _ = s.limits()
    with pytest.raises(ValueError):
        s.buy(max_long + 1, 1.0)
    assert rnd.decision is None


def test_session_ends_after_configured_rounds():
    s = CardSession(EASY.replace(seed=9, rounds=2))
    for _ in range(2):
        s.new_round()
        assert not s.finished
        s.pass_(1.0)
    assert s.finished
    with pytest.raises(RuntimeError):
        s.new_round()


def test_session_ends_early_when_broke():
    # The budget rule caps any loss at the balance, so the only way out is landing exactly on 0.
    s = CardSession(EASY.replace(seed=1, rounds=4))
    s.new_round()
    s.pass_(1.0)
    assert not s.finished
    s.balance = 0
    assert s.finished and s.end_reason == BROKE
    with pytest.raises(RuntimeError):
        s.new_round()


def test_session_ends_when_out_of_risk_capacity():
    s = CardSession(EASY.replace(seed=1, rounds=4))
    s.new_round()
    s.pass_(1.0)
    assert s.end_reason is None
    s.balance = 1  # positive, but too small to cover a 1-unit worst case on either side
    assert s.new_round() is None
    assert s.finished and s.end_reason == OUT_OF_RISK
    assert len(s.rounds) == 1  # the untradable round is never played
    with pytest.raises(RuntimeError):
        s.new_round()


def test_out_of_risk_on_the_very_first_round():
    s = CardSession(MEDIUM.replace(seed=5, budget=1))
    assert s.new_round() is None
    assert s.finished and s.end_reason == OUT_OF_RISK and s.rounds == []


def test_tradable_round_is_not_out_of_risk():
    s = CardSession(EASY.replace(seed=1))
    rnd = s.new_round()
    assert rnd is not None and max(s.limits()) >= 1 and not s.finished


def test_worst_case_loss_never_exceeds_balance():
    for seed in range(200):
        s = CardSession(HARD.replace(seed=seed, budget=40))
        while not s.finished:
            rnd = s.new_round()
            if rnd is None:  # out of risk capacity
                break
            max_long, max_short = s.limits()
            if max_long >= 1:
                s.buy(max_long, 0.5)
            elif max_short >= 1:
                s.sell(max_short, 0.5)
            else:
                s.pass_(0.5)
            assert -rnd.pnl <= rnd.balance_before
            assert s.balance >= 0


def test_timeout_is_logged_at_full_timer():
    s = CardSession(EASY.replace(seed=5))
    rnd = s.new_round()
    s.timeout()
    assert rnd.decision.action == TIMEOUT and rnd.decision.t == 60 and rnd.pnl == 0


def test_flip_reveals_hidden_card_and_recomputes():
    s = CardSession(HARD.replace(seed=21))
    rnd = s.new_round()
    hidden_before = len(rnd.hidden)
    assert rnd.flip_at is not None and 0.3 * 15 <= rnd.flip_at <= 0.6 * 15
    assert not s.advance(rnd.flip_at - 0.01)
    assert s.advance(rnd.flip_at)
    assert len(rnd.hidden) == hidden_before - 1 and rnd.flip_index in rnd.face_up
    assert len(rnd.tape) == (1 if rnd.flip_stale else 2)
    if rnd.doubled is not None:
        assert rnd.doubled in rnd.hidden


def test_stale_quotes_happen_and_requotes_happen():
    stale = []
    for seed in range(40):
        s = CardSession(HARD.replace(seed=seed))
        rnd = s.new_round()
        stale.append(rnd.flip_stale)
    assert any(stale) and not all(stale)


def test_events_every_round_on_hard():
    s = CardSession(HARD.replace(seed=8))
    for _ in range(6):
        rnd = s.new_round()
        assert rnd.event is not None
        if rnd.event == "no_twos":
            assert all(c.rank != 2 for c in rnd.cards)
        s.pass_(0.1)


# ── determinism ──────────────────────────────────────────────────────────────


def _play(config, script):
    s = CardSession(config)
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
        s.report(rnd.pnl, 1.0)
        trace.append((
            [str(c) for c in rnd.cards], list(rnd.face_up), rnd.event, rnd.doubled, rnd.flip_at,
            rnd.flip_index, rnd.flipped_at, rnd.flip_stale, list(rnd.tape), rnd.decision, rnd.settle, rnd.pnl,
        ))
    return s.seed, s.balance, trace


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_same_seed_same_inputs_same_session(preset):
    script = [("buy", 9.0), ("sell", 3.0), ("pass", 12.0), ("buy", 14.0)]
    cfg = preset.replace(seed=1234, rounds=4)
    assert _play(cfg, script) == _play(cfg, script)


def test_different_seeds_differ():
    script = [("pass", 1.0)] * 4
    a = _play(HARD.replace(seed=1, rounds=4), script)
    b = _play(HARD.replace(seed=2, rounds=4), script)
    assert a[2] != b[2]


def test_random_seed_is_recorded_and_replayable():
    s = CardSession(EASY)
    assert isinstance(s.seed, int)
    replay = CardSession(EASY.replace(seed=s.seed))
    assert [str(c) for c in s.new_round().cards] == [str(c) for c in replay.new_round().cards]


def test_config_invalid_rejected_by_session():
    with pytest.raises(ValueError):
        CardSession(CardConfig(face_up_max=4))
