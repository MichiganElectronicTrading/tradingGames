"""Higher or Lower stage 1: decks, Kelly, grading, multipliers, points, payout, bonus, benchmark."""

import math
import random
from fractions import Fraction as F

import pytest

from met_games.games.hilo.config import EASY, FULL, HARD, INTERVIEW, MEDIUM, PRESETS, REDBLACK, HiloConfig
from met_games.games.hilo.model import (
    BLACK,
    DISCIPLINE,
    FAST,
    GOOD,
    HIGHER,
    LIGHTNING,
    LOWER,
    MISS,
    NORMAL,
    OK,
    PERFECT,
    RED,
    SAT_OUT,
    Card,
    Odds,
    benchmark,
    build_deck,
    capital_bonus,
    combo_multiplier,
    grade,
    next_streak,
    odds_hilo,
    odds_redblack,
    pct,
    points,
    settle,
    snap_stake,
    speed_tier,
    stake_amount,
)

C = Card


def full_deck():
    return [C(r, s) for s in "♠♥♦♣" for r in range(1, 14)]


# ── decks ────────────────────────────────────────────────────────────────────


def test_deck_contents():
    rng = random.Random(1)
    interview = build_deck(INTERVIEW, rng)
    assert sorted(c.rank for c in interview) == list(range(1, 14))
    full = build_deck(FULL, rng)
    assert len(full) == 52 and len(set(full)) == 52 and all(sum(c.rank == r for c in full) == 4 for r in range(1, 14))
    rb = build_deck(REDBLACK, rng)
    assert len(rb) == 52 and sum(c.red for c in rb) == 26


@pytest.mark.parametrize("kind", [INTERVIEW, FULL, REDBLACK])
def test_same_seed_same_deck_order(kind):
    assert build_deck(kind, random.Random(42)) == build_deck(kind, random.Random(42))
    assert build_deck(kind, random.Random(42)) != build_deck(kind, random.Random(43))


# ── Kelly ────────────────────────────────────────────────────────────────────


def test_kelly_typical_counts():
    left = [c for c in full_deck() if c != C(5, "♠")]  # a 5 showing, full deck otherwise
    o = odds_hilo(C(5, "♠"), left)
    assert (o.h, o.same, o.l) == (32, 3, 16)
    assert o.k == F(16, 48) and o.right == HIGHER and pct(o.k) == 33


def test_kelly_no_edge_when_equal_or_empty():
    o = odds_hilo(C(7, "♠"), [C(3, "♥"), C(10, "♦"), C(7, "♣")])
    assert (o.h, o.same, o.l) == (1, 1, 1) and o.k == 0 and o.right is None
    o = odds_hilo(C(7, "♠"), [C(7, "♥")])  # only a same-rank card left
    assert o.h + o.l == 0 and o.k == 0 and o.right is None


def test_kelly_all_one_side():
    o = odds_hilo(C(13, "♠"), [C(2, "♥"), C(9, "♦"), C(5, "♣")])  # a king showing
    assert o.k == 1 and o.right == LOWER and pct(o.k) == 100


def test_kelly_red_black():
    o = odds_redblack([C(1, "♥"), C(2, "♦"), C(3, "♥"), C(4, "♠")])
    assert (o.h, o.l, o.up, o.down) == (3, 1, RED, BLACK) and o.k == F(1, 2) and o.right == RED
    assert odds_redblack([C(1, "♥"), C(2, "♠")]).k == 0


def test_pct_rounds_half_up():
    assert pct(F(1, 3)) == 33 and pct(F(2, 3)) == 67 and pct(F(1, 8)) == 13  # 12.5 → 13


# ── grading ──────────────────────────────────────────────────────────────────


def edge(k: F) -> Odds:
    """Odds with exactly Kelly k on HIGHER (h + l = 1000)."""
    h = int((1 + k) * 500)
    assert F(h - (1000 - h), 1000) == k
    return Odds(h, 0, 1000 - h, HIGHER, LOWER)


@pytest.mark.parametrize(
    "k,s,expected",
    [
        # big k: tolerances are 10% / 25% of k
        (F(1, 2), F(55, 100), PERFECT), (F(1, 2), F(551, 1000), GOOD),  # ±0.05
        (F(1, 2), F(375, 1000), GOOD), (F(1, 2), F(374, 1000), OK),  # ±0.125
        # small k: the 3 / 7 point floors apply
        (F(1, 10), F(13, 100), PERFECT), (F(1, 10), F(131, 1000), GOOD),  # floor 0.03 (> 0.01)
        (F(1, 10), F(17, 100), GOOD), (F(1, 10), F(171, 1000), OK),  # floor 0.07 (> 0.025)
        (F(1, 10), F(3, 100), GOOD),  # 0.07 under
    ],
)
def test_grade_tolerances(k, s, expected):
    assert grade(edge(k), HIGHER, s) == expected


def test_grade_wrong_side_sat_out_no_edge():
    o = edge(F(1, 2))
    assert grade(o, LOWER, F(1, 2)) == MISS  # wrong side
    assert grade(o, HIGHER, F(0)) == SAT_OUT
    assert grade(o, None, F(0)) == SAT_OUT
    flat = Odds(5, 1, 5, HIGHER, LOWER)
    assert grade(flat, None, F(0)) == DISCIPLINE
    assert grade(flat, HIGHER, F(10, 100)) == MISS  # betting with no edge
    assert grade(o, HIGHER, F(1, 2), timeout=True) == MISS


# ── multipliers + points ─────────────────────────────────────────────────────


def test_speed_tier_edges():
    t = F(10)
    assert speed_tier(F(25, 10), t) == LIGHTNING and speed_tier(F(275, 100), t) == FAST
    assert speed_tier(F(5), t) == FAST and speed_tier(F(525, 100), t) == NORMAL


def test_combo_and_streak():
    assert combo_multiplier(0) == 1 and combo_multiplier(3) == F(13, 10) and combo_multiplier(25) == 3
    assert combo_multiplier(20) == 3 and combo_multiplier(19) == F(29, 10)
    assert next_streak(4, PERFECT) == 5 and next_streak(4, GOOD) == 5 and next_streak(4, DISCIPLINE) == 5
    assert next_streak(4, OK) == 4  # OK leaves it
    assert next_streak(4, MISS) == 0 and next_streak(4, SAT_OUT) == 0


def test_points_use_the_pre_bet_combo_and_speed_only_for_good_grades():
    assert points(PERFECT, LIGHTNING, 0) == 200
    assert points(PERFECT, FAST, 3) == 195  # 100 × 1.5 × 1.3
    assert points(GOOD, NORMAL, 30) == 180  # combo capped at 3.0
    assert points(DISCIPLINE, FAST, 1) == 83  # 50 × 1.5 × 1.1 = 82.5 → half up
    assert points(OK, LIGHTNING, 2) == 24  # no speed for OK: 20 × 1.2
    assert points(MISS, LIGHTNING, 10) == 0 and points(SAT_OUT, FAST, 5) == 0


# ── money ────────────────────────────────────────────────────────────────────


def test_stake_floor_and_settle():
    assert stake_amount(1000, 33) == 330 and stake_amount(999, 33) == 329 and stake_amount(7, 50) == 3
    assert settle(HIGHER, C(5, "♠"), C(9, "♥")) == 1 and settle(HIGHER, C(5, "♠"), C(2, "♥")) == -1
    assert settle(LOWER, C(5, "♠"), C(5, "♥")) == 0  # same rank returns the stake
    assert settle(RED, None, C(5, "♦")) == 1 and settle(BLACK, None, C(5, "♦")) == -1
    assert settle(None, C(5, "♠"), C(9, "♥")) == 0


def test_capital_bonus():
    assert capital_bonus(1000, 2000, False) == 1000
    assert capital_bonus(1000, 1500, False) == round(1000 * math.log2(1.5)) == 585
    assert capital_bonus(1000, 1000, False) == 0 and capital_bonus(1000, 900, False) == 0
    assert capital_bonus(1000, 5000, True) == 0  # bust forfeits it


def test_benchmark_on_a_fixed_deck_order():
    cards = [C(7, "♠"), C(13, "♥"), C(1, "♦"), C(12, "♣")]
    # 7 showing, left K A Q: h=2 l=1 → k=1/3 HIGHER, floor(1000/3)=333, K wins → 1333
    # K showing, left A Q: h=0 l=2 → k=1 LOWER, stake 1333, A wins → 2666
    # A showing, left Q: k=1 HIGHER, stake 2666, Q wins → 5332
    assert benchmark(INTERVIEW, cards, 1000) == F(5332, 1000)
    rb = [C(1, "♥"), C(2, "♠"), C(3, "♥")]  # reds 2 blacks 1: RED 1/3 → 333 win; 1 red 1 black: 0; then RED all-in
    assert benchmark(REDBLACK, rb, 1000) == F(2666, 1000)


# ── config ───────────────────────────────────────────────────────────────────


def test_presets():
    assert (EASY.deck, EASY.board) == (INTERVIEW, "odds")
    assert (MEDIUM.deck, MEDIUM.board) == (FULL, "counts")
    assert (HARD.deck, HARD.board) == (FULL, "minimal")
    assert all(not p.timed and p.time_s == 10 for p in PRESETS.values())  # untimed; 10 s if toggled on in Custom
    assert all(p.summary()["time per bet"] == "untimed" for p in PRESETS.values())
    assert all(p.start_capital == 1000 and p.quick_lock and not p.errors() for p in PRESETS.values())


@pytest.mark.parametrize("changes", [dict(deck="tarot"), dict(time_s=1), dict(time_s=31), dict(board="x"),
                                     dict(start_capital=50), dict(seed="x")])
def test_bad_configs(changes):
    assert EASY.replace(**changes).errors()


def test_round_trip():
    assert HiloConfig.from_dict(HARD.to_dict()) == HARD


@pytest.mark.parametrize("start,up,down", [(0, 25, 0), (13, 25, 0), (25, 50, 0), (60, 75, 50), (100, 100, 75)])
def test_shift_arrows_snap_to_multiples_of_25(start, up, down):
    assert snap_stake(start, 1) == up and snap_stake(start, -1) == down


def test_shift_arrows_walk_the_quarters_and_clamp():
    p = 60
    for want in (75, 100, 100):
        p = snap_stake(p, 1)
        assert p == want
    p = 60
    for want in (50, 25, 0, 0):
        p = snap_stake(p, -1)
        assert p == want
