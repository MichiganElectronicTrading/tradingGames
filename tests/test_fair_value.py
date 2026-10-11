"""Fair value and settle range vs brute force.

The brute force deliberately re-implements the deck and event values instead of importing them,
so it checks the engine against an independent reading of the rules. The exhaustive enumerations
are the proof of exactness; the Monte Carlo case is a sanity check for larger k.
"""

import itertools
import math
import random

import pytest

from met_games.games.card.deck import Card
from met_games.games.card.engine import market_state

SUITS = "♠♥♦♣"
DECK = [Card(rank, suit) for suit in SUITS for rank in range(2, 15)]
EVENTS = [None, "face_ten", "no_twos", "aces_one", "double_hidden", "red_negative"]


def value(card, event):
    v = card.rank
    if event == "face_ten" and v in (11, 12, 13):
        v = 10
    if event == "aces_one" and v == 14:
        v = 1
    if event == "red_negative" and card.suit in "♥♦":
        v = -v
    return v


def pool(up, event):
    deck = [c for c in DECK if not (event == "no_twos" and c.rank == 2)]
    return [c for c in deck if c not in up]


def outcomes(hand_values, event):
    """Possible settlement contributions of one hidden hand (one per doubled card under double_hidden)."""
    s = sum(hand_values)
    if event == "double_hidden":
        return [s + v for v in hand_values]
    return [s]


def brute_force(up, event, k):
    up_sum = sum(value(c, event) for c in up)
    rest = [value(c, event) for c in pool(up, event)]
    total = count = 0.0
    lo, hi = float("inf"), float("-inf")
    for hand in itertools.combinations(rest, k):
        outs = outcomes(hand, event)
        total += sum(outs) / len(outs)  # the doubled card is uniform among the hidden ones
        count += 1
        lo, hi = min(lo, *outs), max(hi, *outs)
    return up_sum + total / count, up_sum + lo, up_sum + hi


MC_DRAWS = 200_000
MC_SEED = 7  # tolerance verified for seeds 0–49; one fixed seed keeps the suite reproducible


def monte_carlo(up, event, k, draws=MC_DRAWS, seed=MC_SEED):
    """Sampled (mean, min, max, sample std) of the settlement."""
    rng = random.Random(seed)
    up_sum = sum(value(c, event) for c in up)
    rest = [value(c, event) for c in pool(up, event)]
    total = total_sq = 0  # integer sums keep the variance exact
    lo, hi = float("inf"), float("-inf")
    for _ in range(draws):
        hand = rng.sample(rest, k)
        out = rng.choice(outcomes(hand, event))
        total += out
        total_sq += out * out
        lo, hi = min(lo, out), max(hi, out)
    std = math.sqrt((total_sq - total * total / draws) / (draws - 1))
    return up_sum + total / draws, up_sum + lo, up_sum + hi, std

C = Card
ALL_BUT_ONE_UP = [C(14, "♥"), C(13, "♠"), C(3, "♦"), C(11, "♣"), C(9, "♥")]  # n=6, k=1
SOME_UP = [C(12, "♦"), C(14, "♣")]  # n=7, k=5


@pytest.mark.parametrize("event", EVENTS)
def test_zero_face_up_matches_enumeration(event):
    m = market_state([], event, 3)
    fair, lo, hi = brute_force([], event, 3)
    assert m.fair == pytest.approx(fair, abs=0.05)
    assert (m.settle_min, m.settle_max) == (lo, hi)


@pytest.mark.parametrize("event", EVENTS)
def test_all_but_one_face_up_matches_enumeration(event):
    m = market_state(ALL_BUT_ONE_UP, event, 1)
    fair, lo, hi = brute_force(ALL_BUT_ONE_UP, event, 1)
    assert m.fair == pytest.approx(fair, abs=0.05)
    assert (m.settle_min, m.settle_max) == (lo, hi)


@pytest.mark.parametrize("event", EVENTS)
def test_two_hidden_matches_enumeration(event):
    up = [C(10, "♥"), C(2, "♣"), C(14, "♦")]
    up = [c for c in up if not (event == "no_twos" and c.rank == 2)]
    m = market_state(up, event, 2)
    fair, lo, hi = brute_force(up, event, 2)
    assert m.fair == pytest.approx(fair, abs=0.05)
    assert (m.settle_min, m.settle_max) == (lo, hi)


@pytest.mark.parametrize("event", EVENTS)
def test_large_k_matches_monte_carlo(event, seed=MC_SEED):
    k = 5
    m = market_state(SOME_UP, event, k)
    fair, lo, hi, std = monte_carlo(SOME_UP, event, k, seed=seed)
    tol = 5 * std / math.sqrt(MC_DRAWS)  # 5 standard errors, sized to this case's variance
    assert m.fair == pytest.approx(fair, abs=tol)
    # sampled extremes must sit inside the analytic range ...
    assert m.settle_min <= lo and hi <= m.settle_max
    # ... and the analytic extremes must be attainable hands
    rest = sorted(value(c, event) for c in pool(SOME_UP, event))
    up_sum = sum(value(c, event) for c in SOME_UP)
    assert m.settle_min == up_sum + min(outcomes(rest[:k], event))
    assert m.settle_max == up_sum + max(outcomes(rest[-k:], event))


def test_no_hidden_cards_is_exact():
    m = market_state(ALL_BUT_ONE_UP, None, 0)
    s = sum(c.rank for c in ALL_BUT_ONE_UP)
    assert (m.fair, m.settle_min, m.settle_max) == (s, s, s)
