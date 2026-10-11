"""Trading Game engine: zero-sum, seats, peeks, private fair vs enumeration, computer traders,
learning, Hard flips, the player's risk rule, P&L split, determinism."""

import random
from itertools import permutations

import pytest
from test_fair_value import brute_force  # Card's enumeration helper

from met_games.games.card.deck import Card
from met_games.games.sumgame.engine import BUY, PASS, SELL, TIMEOUT
from met_games.games.trade.config import EASY, HARD, MEDIUM, PRESETS, TradeConfig
from met_games.games.trade.engine import (
    DELTA,
    GAMMA,
    PLAYERS,
    THETA,
    TRADERS,
    TURNS,
    YOU,
    Action,
    Hand,
    TradeSession,
    computer_quote,
    computer_take,
    flip_schedule,
    peek_assignment,
    worst_loss,
)
from met_games.games.trade.stats import csv_rows, history_record, mistakes, session_stats

C = Card

# ── helpers ──────────────────────────────────────────────────────────────────


def play_turn(s: TradeSession, rng: random.Random) -> None:
    """A random but legal player action for the open turn (driven by its own rng, so replayable)."""
    hand = s.current
    turn = hand.turn
    if turn.maker == YOU:
        cfg = s.config
        w = rng.randint(cfg.width_min, cfg.width_max)
        bid = round(hand.public().fair + rng.uniform(-4, 4)) - w // 2
        size = cfg.FIXED_SIZE if cfg.sizing == "fixed" else rng.randint(1, cfg.SIZE_MAX)
        if s.quote_errors(bid, bid + w, size):
            s.no_quote()
        else:
            s.post_quote(bid, bid + w, size)
        return
    max_buy, max_sell = s.take_limits()
    choice = rng.choice([BUY, SELL, PASS, TIMEOUT])
    if choice == BUY and max_buy:
        s.take(BUY, rng.randint(1, max_buy))
    elif choice == SELL and max_sell:
        s.take(SELL, rng.randint(1, max_sell))
    elif choice == TIMEOUT:
        s.timeout()
    else:
        s.pass_()


def play_hand(s: TradeSession, rng: random.Random, report_ok: bool = True) -> Hand:
    hand = s.new_hand()
    while True:
        play_turn(s, rng)
        if s.next_turn() is None:
            break
    s.report(hand.pnl(YOU) + (0 if report_ok else 1), 1.0)
    return hand


def play_session(cfg: TradeConfig, player_seed: int = 0) -> TradeSession:
    s = TradeSession(cfg)
    rng = random.Random(player_seed)
    while not s.finished:
        play_hand(s, rng)
    return s


def custom_hand(s: TradeSession, cards, n_up, seats, peeks=None, flips=(None, None, None), event=None,
                doubled=None) -> Hand:
    """Put a hand with a known deal at the table and open turn 1 (bypasses the random draws)."""
    hand = Hand(
        number=len(s.hands) + 1, items=list(cards), event=event, doubled=doubled, face_up=list(range(n_up)),
        seats=tuple(seats), peeks=peeks or {t: None for t in TRADERS}, flips=list(flips),
        learn_rate=s.config.learn_rate, balance_before=s.balance,
    )
    s.hands.append(hand)
    s._open_turn(hand, None)
    return hand


# Three cards, all hidden: fair = 3 × deck mean 8 = 24, range 6–42.
ALL_HIDDEN = [C(10, "♠"), C(7, "♥"), C(4, "♣")]


# ── zero-sum + P&L split ────────────────────────────────────────────────────


@pytest.mark.parametrize("preset", list(PRESETS))
def test_hand_pnls_sum_to_zero(preset):
    for seed in range(40):
        s = play_session(PRESETS[preset].replace(seed=seed), player_seed=seed)
        for h in s.hands:
            assert sum(h.pnls().values()) == 0
            assert sum(h.position.values()) == 0 and sum(h.cash.values()) == 0
        assert sum(s.totals.values()) == 0


@pytest.mark.parametrize("preset", list(PRESETS))
def test_making_plus_taking_is_hand_pnl(preset):
    for seed in range(30):
        s = play_session(PRESETS[preset].replace(seed=seed), player_seed=seed + 100)
        for h in s.hands:
            assert h.making_pnl + h.taking_pnl == h.pnl(YOU)
            assert h.balance_after == h.balance_before + h.pnl(YOU)
        assert s.balance == s.config.budget + s.totals[YOU]


# ── seats ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("preset", list(PRESETS))
def test_seat_order_is_a_permutation_and_everyone_makes_once(preset):
    seen = set()
    for seed in range(30):
        s = TradeSession(PRESETS[preset].replace(seed=seed))
        rng = random.Random(seed)
        while not s.finished:
            hand = play_hand(s, rng)
            assert sorted(hand.seats) == sorted(PLAYERS)
            assert [t.maker for t in hand.turns] == list(hand.seats)
            assert len(hand.turns) == TURNS
            seen.add(hand.seats)
    assert len(seen) > 5  # the order really is random


# ── peeks ────────────────────────────────────────────────────────────────────


def test_peeks_distinct_with_three_or_more_hidden():
    for seed in range(50):
        peeks = peek_assignment([4, 5, 6, 7], random.Random(seed), single=False)
        assert set(peeks) == set(TRADERS)
        assert len(set(peeks.values())) == 3 and set(peeks.values()) <= {4, 5, 6, 7}


def test_peeks_wrap_with_fewer_than_three_hidden():
    rng = random.Random(1)
    assert peek_assignment([3, 4], rng, single=False) == {DELTA: 3, GAMMA: 4, THETA: 3}  # j mod 2
    assert peek_assignment([2], rng, single=False) == {DELTA: 2, GAMMA: 2, THETA: 2}


def test_no_hidden_cards_no_peeks():
    assert peek_assignment([], random.Random(1), single=False) == {t: None for t in TRADERS}
    assert peek_assignment([], random.Random(1), single=True) == {t: None for t in TRADERS}


def test_easy_has_a_single_random_peeker():
    peekers = set()
    for seed in range(60):
        s = TradeSession(EASY.replace(seed=seed))
        hand = s.new_hand()
        seen = [t for t in TRADERS if hand.peeks[t] is not None]
        assert len(seen) == (1 if hand.hidden else 0)
        assert all(hand.peeks[t] in hand.hidden for t in seen)
        peekers.update(seen)
    assert peekers == set(TRADERS)


@pytest.mark.parametrize("preset", [MEDIUM, HARD])
def test_medium_and_hard_every_trader_peeks(preset):
    for seed in range(40):
        hand = TradeSession(preset.replace(seed=seed)).new_hand()
        peeked = [hand.peeks[t] for t in TRADERS]
        assert all(p in hand.hidden and p != hand.doubled for p in peeked)
        if len(hand.hidden) - (hand.doubled is not None) >= 3:
            assert len(set(peeked)) == 3


# ── private fair vs enumeration ─────────────────────────────────────────────

FAIR_CASES = [
    # (cards, n_up, event, doubled)
    ([C(9, "♠"), C(13, "♥"), C(2, "♦"), C(6, "♣"), C(11, "♠")], 2, None, None),
    ([C(9, "♠"), C(13, "♥"), C(2, "♦"), C(6, "♣"), C(11, "♠")], 2, "red_negative", None),
    ([C(9, "♠"), C(13, "♥"), C(3, "♦"), C(6, "♣"), C(14, "♠")], 1, "face_ten", None),
    ([C(9, "♠"), C(13, "♥"), C(3, "♦"), C(6, "♣"), C(14, "♠")], 2, "aces_one", None),
    ([C(9, "♠"), C(13, "♥"), C(3, "♦"), C(6, "♣"), C(14, "♠")], 2, "no_twos", None),
    ([C(9, "♠"), C(13, "♥"), C(3, "♦"), C(6, "♣"), C(14, "♠")], 2, "double_hidden", 4),
]


@pytest.mark.parametrize("cards,n_up,event,doubled", FAIR_CASES)
def test_private_fair_matches_enumeration(cards, n_up, event, doubled):
    s = TradeSession(MEDIUM.replace(seed=1))
    hidden = list(range(n_up, len(cards)))
    peeks = {DELTA: hidden[0], GAMMA: hidden[1], THETA: None}  # THETA saw nothing
    hand = custom_hand(s, cards, n_up, (YOU, DELTA, GAMMA, THETA), peeks, event=event, doubled=doubled)
    up = cards[:n_up]
    for trader in (DELTA, GAMMA):
        seen = up + [cards[peeks[trader]]]
        m = hand.private(trader)
        fair, lo, hi = brute_force(seen, event, len(hidden) - 1)
        assert m.fair == pytest.approx(fair, abs=1e-9)
        assert (m.settle_min, m.settle_max) == (lo, hi)
    m = hand.private(THETA)  # no peek: the public view
    fair, lo, hi = brute_force(up, event, len(hidden))
    assert m.fair == pytest.approx(fair, abs=1e-9) and m == hand.public()
    assert (m.settle_min, m.settle_max) == (lo, hi)
    table_fair, _, _ = brute_force(up + [cards[hidden[0]], cards[hidden[1]]], event, len(hidden) - 2)
    assert hand.table().fair == pytest.approx(table_fair, abs=1e-9)


def test_est_is_clamped_to_the_range():
    s = TradeSession(HARD.replace(seed=1))
    hand = custom_hand(s, ALL_HIDDEN, 0, (DELTA, YOU, GAMMA, THETA))
    hand.offsets[GAMMA] = 100.0
    hand.offsets[THETA] = -100.0
    assert (hand.est(GAMMA), hand.est(THETA), hand.est(DELTA)) == (42, 6, 24.0)


# ── computer makers and takers ──────────────────────────────────────────────


def test_computer_quote_formula_and_rounding():
    assert computer_quote(20.0, 24.0, 4) == (20, 24)  # mid 22
    assert computer_quote(20.0, 21.0, 3) == (19, 22)  # mid 20.5 → bid round(19.0)
    assert computer_quote(20.0, 23.0, 2) == (20, 22)  # mid 21.5 → bid round(20.5) = 20 (half to even)
    assert computer_quote(20.0, 25.0, 2) == (22, 24)  # mid 22.5 → bid round(21.5) = 22 (half to even)
    assert computer_quote(30.0, 20.0, 2) == (24, 26)  # est below public: mid 25


def test_session_computer_quote_uses_public_fair_and_est():
    s = TradeSession(MEDIUM.replace(seed=1))
    peeks = {DELTA: 0, GAMMA: None, THETA: None}
    hand = custom_hand(s, ALL_HIDDEN, 0, (DELTA, YOU, GAMMA, THETA), peeks)
    # DELTA saw the 10: private fair = 10 + 2 × (406/51)
    est = hand.est(DELTA)
    assert est == pytest.approx(10 + 2 * 406 / 51)
    mid = 24 + 0.5 * (est - 24)
    t = hand.turn
    assert (t.maker, t.bid, t.ask, t.size) == (DELTA, round(mid - 1), round(mid - 1) + 2, 5)


@pytest.mark.parametrize(
    "est,expected",
    [
        (23.0, (BUY, 5, None)),  # est exactly ask + 1
        (22.999, (PASS, 0, None)),
        (17.0, (SELL, 5, None)),  # est exactly bid − 1
        (17.001, (PASS, 0, None)),
        (20.0, (PASS, 0, None)),
    ],
)
def test_computer_taker_boundaries(est, expected):
    assert computer_take(est, 18, 22, 5, 5) == expected


def test_computer_taker_takes_what_is_left():
    assert computer_take(30.0, 18, 22, 5, 3) == (BUY, 3, None)
    assert computer_take(10.0, 18, 22, 2, 5) == (SELL, 2, None)
    assert computer_take(30.0, 18, 22, 5, 0) == (PASS, 0, BUY)  # wanted to buy, nothing left


def test_size_depletes_when_traders_hit_the_same_side():
    s = TradeSession(MEDIUM.replace(seed=1))
    hand = custom_hand(s, ALL_HIDDEN, 0, (YOU, DELTA, GAMMA, THETA))
    s.post_quote(17, 19, 7)  # every trader (est 24) wants the 19 ask
    t = hand.turn
    assert [(a.who, a.action, a.size, a.price) for a in t.actions] == [
        (DELTA, BUY, 5, 19), (GAMMA, BUY, 2, 19), (THETA, PASS, 0, None),
    ]
    assert t.actions[2].wanted == BUY
    assert (t.ask_left, t.bid_left, t.ask_filled, t.bid_filled) == (0, 7, 7, 0)
    assert hand.position[YOU] == -7 and hand.cash[YOU] == 7 * 19


def test_player_acts_before_the_traders():
    s = TradeSession(MEDIUM.replace(seed=1))
    hand = custom_hand(s, ALL_HIDDEN, 0, (GAMMA, THETA, YOU, DELTA))
    t = hand.turn
    assert t.maker == GAMMA and t.actions == []  # traders wait for you
    max_buy, _ = s.take_limits()
    s.take(BUY, max_buy)
    assert [a.who for a in t.actions] == [YOU, THETA, DELTA]  # you, then seat order
    assert t.actions[0].size == 5 and t.ask_left == 0
    assert all(a.size == 0 or a.action == SELL for a in t.actions[1:])  # nothing left on the ask for them
    with pytest.raises(RuntimeError):
        s.pass_()


def test_traders_act_in_seat_order_on_your_market():
    s = TradeSession(MEDIUM.replace(seed=1))
    hand = custom_hand(s, ALL_HIDDEN, 0, (THETA, DELTA, YOU, GAMMA))
    assert hand.turn.maker == THETA
    s.pass_()
    s.next_turn()
    s.pass_()
    s.next_turn()
    assert hand.turn.maker == YOU
    s.post_quote(23, 25, 1)
    assert [a.who for a in hand.turn.actions] == [THETA, DELTA, GAMMA]


# ── learning ─────────────────────────────────────────────────────────────────


def test_learning_hand_computed():
    s = TradeSession(HARD.replace(seed=1))
    hand = custom_hand(s, ALL_HIDDEN, 0, (YOU, DELTA, GAMMA, THETA))
    assert all(hand.est(t) == 24.0 for t in TRADERS)
    s.post_quote(19, 22, 10)
    # DELTA (est 24 ≥ 23) buys 5 @ 22, target 23: offset += 0.25 × (23 − 24) = −0.25 → est 23.75
    # GAMMA (est 23.75 ≥ 23) buys 5 @ 22: offset += 0.25 × (23 − 23.75) = −0.1875 → −0.4375, est 23.5625
    # THETA wants the ask, but it's gone: passes, no fill, no update
    t = hand.turn
    assert [(a.who, a.action, a.size) for a in t.actions] == [(DELTA, BUY, 5), (GAMMA, BUY, 5), (THETA, PASS, 0)]
    assert hand.offsets == {DELTA: -0.4375, GAMMA: -0.4375, THETA: -0.4375}
    assert hand.est(THETA) == 23.5625
    # DELTA's market next: bid = round(24 + 0.5 × (23.5625 − 24) − 1) = round(22.78125) = 23
    s.next_turn()
    t = hand.turn
    assert (t.maker, t.bid, t.ask) == (DELTA, 23, 25)
    # you sell 1 into the 23 bid: target 22, every offset += 0.25 × (22 − 23.5625) = −0.390625
    s.take(SELL, 1)
    assert t.actions[0] == Action(YOU, SELL, 1, 23, 24.0)
    # GAMMA (est 23.171875) and THETA pass: neither ≥ 26 nor ≤ 22
    assert hand.offsets == {DELTA: -0.828125, GAMMA: -0.828125, THETA: -0.828125}
    assert [a.action for a in t.actions[1:]] == [PASS, PASS]


@pytest.mark.parametrize("preset", [EASY, MEDIUM])
def test_no_learning_on_easy_and_medium(preset):
    fills = 0
    for seed in range(20):
        s = TradeSession(preset.replace(seed=seed))
        rng = random.Random(seed)
        hand = s.new_hand()
        while True:
            play_turn(s, rng)
            fills += len(hand.turn.fills)
            assert all(v == 0.0 for v in hand.offsets.values())
            if s.next_turn() is None:
                break
    assert fills > 0  # there were fills to learn from


def test_learning_resets_each_hand():
    s = TradeSession(HARD.replace(seed=4))
    rng = random.Random(4)
    for _ in range(3):
        hand = s.new_hand()
        assert all(v == 0.0 for v in hand.offsets.values())
        while True:
            play_turn(s, rng)
            if s.next_turn() is None:
                break
        s.report(hand.pnl(YOU), 1.0)


# ── Hard flips ───────────────────────────────────────────────────────────────


def test_flip_schedule_never_flips_the_last_hidden_card():
    rng = random.Random(0)
    assert flip_schedule([], None, rng) == [None, None, None]
    assert flip_schedule([4], None, rng) == [None, None, None]
    two = flip_schedule([3, 4], None, rng)
    assert two[0] in (3, 4) and two[1:] == [None, None]
    assert flip_schedule([3, 4], 4, rng) == [3, None, None]  # the doubled card stays hidden
    for seed in range(50):
        flips = flip_schedule([2, 3, 4, 5], 3, random.Random(seed))
        assert None not in flips and 3 not in flips and len(set(flips)) == 3


def test_hard_flips_update_public_and_private_fair():
    peeked_flip_seen = False
    for seed in range(80):
        s = TradeSession(HARD.replace(seed=seed))
        rng = random.Random(seed)
        hand = s.new_hand()
        while True:
            play_turn(s, rng)
            before = len(hand.hidden)
            t = s.next_turn()
            if t is None:
                break
            assert len(hand.hidden) >= 1  # never the last hidden card
            if hand.doubled is not None:
                assert hand.doubled in hand.hidden
            assert t.up == tuple(hand.face_up)
            if t.flipped is None:
                assert len(hand.hidden) == before
                continue
            assert len(hand.hidden) == before - 1 and hand.face_up[-1] == t.flipped
            up = [hand.items[i] for i in hand.face_up]
            assert hand.public() == hand.SOURCE.market(up, hand.event, len(hand.hidden))
            for trader in TRADERS:
                if hand.peeks[trader] == t.flipped:  # the peeker's edge is now public
                    peeked_flip_seen = True
                    assert hand.private(trader) == hand.public()
                elif hand.peeks[trader] in hand.hidden:  # still private
                    assert hand.private(trader) != hand.public()
        s.report(hand.pnl(YOU), 1.0)
    assert peeked_flip_seen


def test_no_flips_off_hard():
    for preset in (EASY, MEDIUM):
        for seed in range(20):
            s = TradeSession(preset.replace(seed=seed))
            hand = play_hand(s, random.Random(seed))
            assert hand.flips == [None, None, None] and all(t.flipped is None for t in hand.turns)


# ── the player's risk rule ──────────────────────────────────────────────────


def test_worst_loss_is_at_an_end_of_the_range():
    assert worst_loss(-100, 5, 6, 42) == 70  # long 5 bought at 20: worst at 6
    assert worst_loss(100, -5, 6, 42) == 110  # short 5 sold at 20: worst at 42
    assert worst_loss(10, 0, 6, 42) == 0


def test_quote_rejected_when_worst_case_breaches_balance():
    s = TradeSession(EASY.replace(seed=1, budget=60))
    hand = custom_hand(s, ALL_HIDDEN, 0, (YOU, DELTA, GAMMA, THETA))
    risk = dict(s.quote_risk(20, 24, 5))
    assert risk == {"bid fills": 70, "ask fills": 90, "both fill": 0}  # (20−6)×5, (42−24)×5
    errs = s.quote_errors(20, 24, 5)
    assert errs and "worst case" in errs[0] and "$60" in errs[0]
    with pytest.raises(ValueError):
        s.post_quote(20, 24, 5)
    assert not hand.turn.posted and not hand.turn.done
    assert s.quote_errors(20, 21, 5)[0].startswith("width 1")  # Easy allows 2–6
    assert "fixed at 5" in s.quote_errors(10, 12, 3)[0]
    s.balance = 90
    assert s.quote_errors(20, 24, 5) == []


def test_take_size_capped_and_side_disabled():
    s = TradeSession(MEDIUM.replace(seed=1, budget=50))
    hand = custom_hand(s, ALL_HIDDEN, 0, (DELTA, YOU, GAMMA, THETA))
    t = hand.turn
    assert (t.bid, t.ask) == (23, 25)
    # buying n: worst at 6 = (25 − 6) × n → ⌊50/19⌋ = 2; selling n: worst at 42 = (42 − 23) × n → 2
    assert s.take_limits() == (2, 2)
    with pytest.raises(ValueError):
        s.take(BUY, 3)
    s.balance = 18  # can't cover one unit on either side
    assert s.take_limits() == (0, 0)
    with pytest.raises(ValueError):
        s.take(SELL, 1)
    s.pass_()


def test_existing_position_counts_toward_the_risk_rule():
    s = TradeSession(MEDIUM.replace(seed=1, budget=100))
    hand = custom_hand(s, ALL_HIDDEN, 0, (DELTA, GAMMA, YOU, THETA))
    s.take(BUY, 5)  # long 5 @ 25: worst at 6 = 95
    assert s.worst_after(0, 0) == 95
    s.next_turn()
    max_buy, max_sell = s.take_limits()
    assert max_buy == 0  # one more long unit breaches $100
    assert max_sell == hand.turn.bid_left  # selling reduces the risk


def test_worst_case_never_exceeds_balance():
    for seed in range(60):
        s = play_session(HARD.replace(seed=seed, budget=60), player_seed=seed)
        for h in s.hands:
            assert -h.pnl(YOU) <= h.balance_before
        assert s.balance >= 0


# ── reports, timeouts, mistakes ─────────────────────────────────────────────


def test_report_exact_integer():
    s = TradeSession(EASY.replace(seed=2))
    hand = s.new_hand()
    rng = random.Random(2)
    while True:
        play_turn(s, rng)
        if s.next_turn() is None:
            break
    with pytest.raises(ValueError):
        s.report("abc", 1.0)
    assert hand.reported is None
    assert s.report(str(hand.pnl(YOU) + 1), 1.0) is False
    assert hand.report_correct is False
    with pytest.raises(RuntimeError):
        s.report(hand.pnl(YOU), 1.0)


def test_no_quote_and_timeout_are_recorded_as_mistakes():
    s = TradeSession(EASY.replace(seed=1, rounds=1))
    hand = custom_hand(s, ALL_HIDDEN, 0, (YOU, DELTA, GAMMA, THETA))
    s.no_quote()
    assert hand.turn.timed_out and not hand.turn.actions
    s.next_turn()
    s.timeout()
    assert hand.turn.actions[0].action == TIMEOUT
    for _ in range(2):
        s.next_turn()
        s.pass_()
    assert s.next_turn() is None and s.finished
    s.report(hand.pnl(YOU) + 1, 1.0)
    errs = mistakes(s)
    assert any("posted no market" in e for e in errs)
    assert any("timed out on DELTA" in e for e in errs)
    assert any("reported P&L" in e for e in errs)


def test_losing_market_mistake_counts_peeker_units():
    s = TradeSession(MEDIUM.replace(seed=1, rounds=1))
    peeks = {DELTA: 0, GAMMA: None, THETA: None}  # DELTA saw the 10
    hand = custom_hand(s, [C(10, "♠"), C(13, "♥"), C(12, "♣")], 0, (YOU, DELTA, GAMMA, THETA), peeks)
    s.post_quote(22, 24, 10)  # DELTA (est > 25) and the others (est 24 → pass) …
    while s.next_turn() is not None:
        s.pass_()
    s.report(hand.pnl(YOU), 1.0)
    assert hand.making_pnl < 0
    units = sum(a.size for a in hand.turns[0].fills if a.who == DELTA)
    assert units > 0
    assert any(f"took {units} unit" in e for e in mistakes(s))


def test_negative_edge_take_is_a_mistake():
    s = TradeSession(MEDIUM.replace(seed=1, rounds=1))
    hand = custom_hand(s, ALL_HIDDEN, 0, (DELTA, YOU, GAMMA, THETA))
    s.take(BUY, 1)  # 25 vs table fair 24
    while s.next_turn() is not None:
        if hand.turn.maker == YOU:
            s.no_quote()
        else:
            s.pass_()
    s.report(hand.pnl(YOU), 1.0)
    assert any("vs table fair 24.00" in e and "-$1.00" in e for e in mistakes(s))


# ── determinism ──────────────────────────────────────────────────────────────


def trace(cfg: TradeConfig, player_seed: int):
    s = play_session(cfg, player_seed)
    hands = [
        ([str(c) for c in h.items], list(h.face_up), h.event, h.doubled, h.seats, h.peeks, h.flips,
         [(t.maker, t.bid, t.ask, t.size, t.actions, t.flipped) for t in h.turns], h.pnls(), dict(h.offsets))
        for h in s.hands
    ]
    return s.seed, s.balance, dict(s.totals), hands


@pytest.mark.parametrize("preset", list(PRESETS))
def test_same_seed_same_inputs_same_session(preset):
    cfg = PRESETS[preset].replace(seed=1234)
    assert trace(cfg, 9) == trace(cfg, 9)
    assert trace(cfg, 9) != trace(PRESETS[preset].replace(seed=1235), 9)


def test_traders_make_no_random_choices():
    """With the same deal, the traders' quotes and fills depend only on game state."""
    s = TradeSession(HARD.replace(seed=5))
    hand = s.new_hand()
    state = s.rng.getstate()
    rng = random.Random(1)
    while True:
        play_turn(s, rng)
        if s.next_turn() is None:
            break
    assert s.rng.getstate() == state  # nothing after the deal touched the session rng


# ── config, stats, records ──────────────────────────────────────────────────


def test_presets_match_table():
    assert (EASY.n_cards_min, EASY.n_cards_max, EASY.face_up_min, EASY.face_up_max, EASY.hands) == (3, 3, 0, 1, 4)
    assert (EASY.quote_timer_s, EASY.take_timer_s, EASY.width_min, EASY.width_max) == (45, 30, 2, 6)
    assert (EASY.sizing, EASY.trader_width, EASY.peeks, EASY.flip_between_turns, EASY.learn_rate) == (
        "fixed", 4, "one", False, 0)
    assert (MEDIUM.n_cards_min, MEDIUM.face_up_max, MEDIUM.hands, MEDIUM.quote_timer_s, MEDIUM.take_timer_s) == (
        5, 2, 4, 30, 20)
    assert (MEDIUM.width_min, MEDIUM.width_max, MEDIUM.sizing, MEDIUM.trader_width, MEDIUM.peeks) == (
        1, 4, "choose", 2, "all")
    assert (HARD.n_cards_min, HARD.n_cards_max, HARD.face_up_min, HARD.face_up_max, HARD.hands) == (6, 8, 1, 3, 6)
    assert (HARD.quote_timer_s, HARD.take_timer_s, HARD.width_min, HARD.width_max, HARD.trader_width) == (
        15, 10, 1, 3, 2)
    assert HARD.flip_between_turns and HARD.learn_rate == 0.25 and HARD.event_freq == 1.0
    assert len(HARD.enabled_events) == 5 and EASY.event_freq == MEDIUM.event_freq == 0
    assert all(p.budget == 500 and not p.errors() for p in PRESETS.values())


@pytest.mark.parametrize(
    "changes,msg",
    [
        (dict(width_min=0), "allowed width"),
        (dict(width_min=5, width_max=4), "allowed width"),
        (dict(width_max=9), "allowed width"),
        (dict(quote_timer_s=4), "quote timer"),
        (dict(peeks="two"), "peeks"),
        (dict(learn_rate=1.5), "learn rate"),
        (dict(rounds=0), "hands must be"),
        (dict(timer_s=200), "take timer must be"),
        (dict(spread=9), "trader width must be"),
    ],
)
def test_bad_configs_rejected(changes, msg):
    errs = EASY.replace(**changes).errors()
    assert any(msg in e for e in errs), errs
    with pytest.raises(ValueError):
        TradeSession(EASY.replace(**changes))


def test_config_round_trip_and_type():
    assert TradeConfig.from_dict(HARD.to_dict()) == HARD
    from met_games.games.card.config import EASY as CARD_EASY

    with pytest.raises(TypeError):
        TradeSession(CARD_EASY)


def test_history_record_and_csv():
    s = play_session(EASY.replace(seed=3), player_seed=3)
    rec = history_record(s)
    st = session_stats(s)
    assert rec["game"] == "trade" and rec["seed"] == 3 and rec["rounds_played"] == 4
    assert rec["final_balance"] == s.balance == 500 + st.making + st.taking
    assert rec["reports_total"] == 4 and "edge_taken" in rec
    rows = csv_rows(s)
    assert rows[0][0] == "hand" and len(rows) > 1 + 4 * 4
    assert {r[0] for r in rows[1:]} == {1, 2, 3, 4}
