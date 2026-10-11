"""Higher or Lower stage 2: the state machine — bets per deck, the clock and timeouts, locking, payouts,
streaks, bust."""

import random
from fractions import Fraction as F

import pytest

from met_games.games.hilo.config import EASY, FULL, HARD, INTERVIEW, MEDIUM, REDBLACK
from met_games.games.hilo.engine import BET, OVER, REVEAL, HiloGame, ticks
from met_games.games.hilo.model import (
    BLACK,
    DISCIPLINE,
    FAST,
    HIGHER,
    LIGHTNING,
    LOWER,
    MISS,
    NORMAL,
    PERFECT,
    RED,
    Card,
    pct,
)

C = Card
TIMED = EASY.replace(timed=True)  # the Custom "timed bets" toggle: the clock, timeouts and speed tiers


def rigged(cards, cfg=EASY):
    """A game playing a fixed deck order."""
    g = HiloGame(cfg.replace(seed=1))
    g.cards = list(cards)
    return g


def play_kelly(g):
    """Bet the right side at k (rounded %), instantly, to the end."""
    while g.phase != OVER:
        o = g.odds()
        g.lock(o.right, pct(o.k) if o.right else 0)
        g.next_bet()
    return g


# ── decks + flow ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("deck,bets", [(INTERVIEW, 12), (FULL, 51), (REDBLACK, 52)])
def test_bets_per_deck(deck, bets):
    g = HiloGame(EASY.replace(deck=deck, seed=3))
    assert g.total_bets == bets
    play_kelly(g)
    assert g.phase == OVER and (len(g.bets) == bets or g.bust)


def test_first_card_showing_and_progression():
    g = HiloGame(EASY.replace(seed=5))
    assert g.showing == g.cards[0] and g.number == 1 and len(g.left) == 12
    bet = g.lock(HIGHER, 10)
    assert bet.showing == g.cards[0] and bet.next == g.cards[1] and g.phase == REVEAL
    g.next_bet()
    assert g.showing == g.cards[1] and g.number == 2 and g.phase == BET


def test_red_black_bets_every_card_with_nothing_showing():
    g = HiloGame(EASY.replace(deck=REDBLACK, seed=5))
    assert g.showing is None and g.sides == (RED, BLACK) and len(g.left) == 52
    with pytest.raises(ValueError):
        g.lock(HIGHER, 10)
    bet = g.lock(RED, 0)
    assert bet.next == g.cards[0] and bet.grade == DISCIPLINE  # 26/26: no edge, sat out


def test_lock_validation():
    g = HiloGame(EASY.replace(seed=5))
    for side, p in ((HIGHER, 101), (HIGHER, -1), (None, 10), ("UP", 10), (HIGHER, 5.5)):
        with pytest.raises(ValueError):
            g.lock(side, p)
    assert g.phase == BET and not g.bets


# ── clock ────────────────────────────────────────────────────────────────────


def test_speed_tiers_on_the_bet_clock():
    g = rigged([C(2, "♠"), C(9, "♥"), C(10, "♦"), C(11, "♣"), C(12, "♠")], TIMED)  # always higher
    g.advance(ticks(2.5))  # 25% of 10 s
    assert g.lock(HIGHER, 100).tier == LIGHTNING
    g.next_bet()
    g.advance(ticks(2.75))
    assert g.lock(HIGHER, 100).tier == FAST
    g.next_bet()
    g.advance(ticks(5))
    assert g.lock(HIGHER, 100).tier == FAST
    g.next_bet()
    g.advance(ticks(5.25))
    assert g.lock(HIGHER, 100).tier == NORMAL


def test_timeout_is_a_stake_zero_miss_and_resets_the_streak():
    g = rigged([C(2, "♠"), C(9, "♥"), C(10, "♦"), C(1, "♣")], TIMED)
    assert g.lock(HIGHER, 33).grade == PERFECT  # k = 1/3
    g.next_bet()
    assert g.streak == 1
    g.advance(ticks(EASY.time_s) - 1)
    assert g.phase == BET and g.seconds_left() == 0.25
    g.advance()
    bet = g.bets[-1]
    assert bet.timeout and bet.grade == MISS and bet.percent == 0 and bet.change == 0 and bet.points == 0
    assert g.streak == 0 and g.phase == REVEAL


def test_no_timeout_ever_fires_untimed():
    g = rigged([C(2, "♠"), C(9, "♥"), C(10, "♦"), C(1, "♣")])
    assert not g.config.timed
    g.advance(ticks(3600))  # an hour on one bet
    assert g.phase == BET and g.bets == []
    b = g.lock(HIGHER, 33)
    assert not b.timeout and b.grade == PERFECT and b.tier == NORMAL
    g.next_bet()
    g.advance(ticks(3600))
    assert g.phase == BET and len(g.bets) == 1


def test_untimed_bet_earns_base_times_combo_with_no_speed_multiplier():
    g = rigged([C(13, "♠"), C(2, "♥"), C(1, "♦"), C(3, "♣")])  # king showing: k = 1 LOWER
    b = g.lock(LOWER, 100)  # instantly — would be LIGHTNING ×2 if timed
    assert (b.grade, b.tier, b.points) == (PERFECT, NORMAL, 100)
    g.next_bet()
    g.lock(None, 0)  # 2 showing, left A 3: no edge → DISCIPLINE 50 × combo ×1.1
    assert (g.bets[-1].grade, g.bets[-1].tier, g.bets[-1].points) == (DISCIPLINE, NORMAL, 55)


def test_the_timed_toggle_restores_the_clock_and_speed():
    g = rigged([C(13, "♠"), C(2, "♥"), C(1, "♦"), C(3, "♣")], TIMED)
    assert g.lock(LOWER, 100).points == 200  # LIGHTNING ×2
    g.next_bet()
    g.advance(ticks(TIMED.time_s))
    assert g.bets[-1].timeout and g.bets[-1].grade == MISS


def test_the_reveal_pause_does_not_use_the_next_bets_clock():
    g = rigged([C(2, "♠"), C(9, "♥"), C(10, "♦"), C(11, "♣")], TIMED)
    g.lock(HIGHER, 100)
    g.advance(100)  # a long reveal flash
    assert g.phase == REVEAL
    g.next_bet()
    assert g.elapsed() == 0 and g.seconds_left() == EASY.time_s


# ── money + scoring ──────────────────────────────────────────────────────────


def test_win_loss_push_with_integer_floors():
    g = rigged([C(5, "♠"), C(9, "♥"), C(9, "♦"), C(2, "♣"), C(3, "♠")], EASY.replace(start_capital=999))
    b = g.lock(HIGHER, 33)  # floor(999 × 0.33) = 329, 9 > 5 wins
    assert (b.amount, b.result, g.capital) == (329, 1, 1328)
    g.next_bet()
    b = g.lock(LOWER, 50)  # same rank: stake returned
    assert (b.amount, b.result, g.capital) == (664, 0, 1328)
    g.next_bet()
    b = g.lock(HIGHER, 25)  # 2 < 9: loses 332
    assert (b.result, g.capital) == (-1, 996)


def test_perfect_kelly_bet_scores_with_speed_and_combo():
    g = rigged([C(13, "♠"), C(2, "♥"), C(1, "♦"), C(3, "♣")], TIMED)  # king showing: k = 1 LOWER
    b = g.lock(LOWER, 100)
    assert (b.grade, b.tier, b.points, g.capital) == (PERFECT, LIGHTNING, 200, 2000)
    g.next_bet()
    b = g.lock(LOWER, 34)  # 2 showing, left A 3: no edge... h=1, l=1 → k = 0, betting is a MISS
    assert b.odds.k == 0 and b.grade == MISS and g.streak == 0


def test_bust_ends_the_game_and_forfeits_the_bonus():
    g = rigged([C(2, "♠"), C(1, "♥"), C(10, "♦"), C(11, "♣")])
    g.lock(HIGHER, 100)  # all in on higher, an ace comes
    assert g.capital == 0 and g.bust and g.bonus == 0
    g.next_bet()
    assert g.phase == OVER and len(g.bets) == 1 < g.total_bets
    assert g.score == g.bet_points


def test_capital_bonus_counts_when_finished_up():
    g = play_kelly(HiloGame(EASY.replace(seed=11)))
    if not g.bust and g.capital > g.start:
        assert g.bonus > 0 and g.score == g.bet_points + g.bonus
    assert g.multiple == F(g.capital, g.start)


def test_same_seed_same_game():
    def trace(seed, preset):
        g = play_kelly(HiloGame(preset.replace(seed=seed)))
        return g.cards, [(b.side, b.percent, b.grade, b.points, b.capital_after) for b in g.bets], g.score

    for preset in (EASY, MEDIUM, HARD, EASY.replace(deck=REDBLACK)):
        assert trace(21, preset) == trace(21, preset)
        assert trace(21, preset)[0] != trace(22, preset)[0]


def test_streak_tracking():
    g = rigged([C(13, "♠"), C(1, "♥"), C(13, "♦"), C(2, "♣"), C(12, "♠")])
    for _ in range(3):
        o = g.odds()
        g.lock(o.right, pct(o.k))
        g.next_bet()
    assert g.best_streak >= 3 and g.best_combo >= F(12, 10)


def test_random_play_never_breaks():
    rng = random.Random(0)
    for seed in range(40):
        g = HiloGame(HARD.replace(seed=seed, deck=rng.choice([INTERVIEW, FULL, REDBLACK])))
        while g.phase != OVER:
            g.advance(rng.randint(0, 20))
            if g.phase == BET:
                side = rng.choice(g.sides + (None,))
                g.lock(side, 0 if side is None else rng.randint(0, 100))
            if g.phase == REVEAL:
                g.next_bet()
        assert g.capital >= 0 and g.score >= 0 and len(g.bets) <= g.total_bets


def test_red_black_bets_never_show_a_card():
    g = HiloGame(EASY.replace(deck=REDBLACK, seed=1))
    for _ in range(3):
        g.lock(RED, 0)
        g.next_bet()
    assert g.showing is None and all(b.showing is None for b in g.bets)
