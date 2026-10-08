"""Outcry stage 1: the number model, the reveal schedule, and exact fair value.

Fair value is checked two ways:
- exactly, against a brute force that enumerates every hidden range, every value of the unknown
  numbers, and every way the lowest/highest copies could have been marked (an independent
  implementation of the same posterior);
- statistically, per the spec: simulate whole games with the real setup code, keep the ones whose
  observed knowledge matches, and compare means within 5 standard errors.
"""

import math
import random
from collections import defaultdict
from itertools import product

import pytest

from mtt_games.games.outcry.config import EASY, HARD, MEDIUM, OutcryConfig
from mtt_games.games.outcry.model import (
    HIGHEST,
    LOWEST,
    Knowledge,
    SeenReveal,
    Universe,
    draw_setup,
    extreme_rounds,
    fair_view,
    knowledge_of,
    range_pairs,
)

R = SeenReveal

# ── brute force ──────────────────────────────────────────────────────────────


def marking_probability(seats):
    """P(the lowest/highest copies were marked consistently with what was seen), by enumeration.
    seats: (value, eligible, role). The lowest copy is uniform over the argmin seats, the highest over
    the argmax seats other than it."""
    vals = [v for v, _, _ in seats]
    lows = [i for i, v in enumerate(vals) if v == min(vals)]
    has_low = any(role == LOWEST for _, _, role in seats)
    has_high = any(role == HIGHEST for _, _, role in seats)
    total = 0.0
    for lo in lows:
        highs = [i for i, v in enumerate(vals) if v == max(vals) and i != lo]
        for hi in highs:
            ok_lo = seats[lo][2] == LOWEST if has_low else seats[lo][1]
            ok_hi = seats[hi][2] == HIGHEST if has_high else seats[hi][1]
            if ok_lo and ok_hi:
                total += 1 / (len(lows) * len(highs))
    return total


def brute_force(k: Knowledge, u: Universe):
    seats = k.seats()
    ksum = sum(v for v, _, _ in seats)
    num = den = 0.0
    ls, us = [], []
    for low, high in range_pairs(u.lo, u.hi, u.min_width):
        if any(not low <= v <= high for v, _, _ in seats):
            continue
        pair = 0.0
        for cfg in product(range(low, high + 1), repeat=k.unknown):
            all_seats = list(seats) + [(v, True, None) for v in cfg]
            f = marking_probability(all_seats) if k.schedule else 1.0
            w = (high - low + 1) ** -k.players * f
            num += w * (ksum + sum(cfg))
            den += w
            pair += w
        if pair > 0:
            ls.append(low)
            us.append(high)
    return num / den, (min(ls), max(ls)), (min(us), max(us))


SMALL = Universe(0, 10, 3)

BRUTE_CASES = {
    "own number only": Knowledge(5, (), 4),
    "several reveals, no extreme yet": Knowledge(4, (R(7, None, False), R(2, None, False)), 5),
    "a reveal ties your number": Knowledge(4, (R(4, None, False),), 4),
    "lowest revealed": Knowledge(6, (R(8, None, False), R(3, LOWEST, False)), 5),
    "highest revealed first": Knowledge(3, (R(5, None, False), R(9, HIGHEST, False)), 5),
    "both extremes revealed": Knowledge(5, (R(2, LOWEST, False), R(9, HIGHEST, False)), 5),
    "you tie the lowest": Knowledge(2, (R(2, LOWEST, False), R(9, HIGHEST, False)), 5),
    "your number revealed": Knowledge(6, (R(6, None, True), R(3, None, False)), 5),
    "your number is the lowest": Knowledge(3, (R(7, None, False), R(3, LOWEST, True)), 5),
    "your number is the highest": Knowledge(9, (R(1, LOWEST, False), R(9, HIGHEST, True)), 5),
    "nothing unknown": Knowledge(5, (R(2, LOWEST, False), R(8, HIGHEST, False)), 3),
    "schedule off": Knowledge(5, (R(7, None, False), R(2, None, False)), 5, schedule=False),
}


@pytest.mark.parametrize("name", list(BRUTE_CASES))
def test_fair_and_bounds_match_brute_force(name):
    k = BRUTE_CASES[name]
    fair, l_bounds, u_bounds = brute_force(k, SMALL)
    view = fair_view(k, SMALL)
    assert view.fair == pytest.approx(fair, abs=1e-9)
    assert (view.l_bounds, view.u_bounds) == (l_bounds, u_bounds)
    assert view.range_seen == (min(k.known), max(k.known))


def test_fair_with_nothing_unknown_is_the_sum():
    assert fair_view(BRUTE_CASES["nothing unknown"], SMALL).fair == pytest.approx(15)


def test_unlabeled_reveals_carry_information():
    """A random reveal is never an extreme, so seeing a new high pushes fair up versus ignoring that."""
    with_rule = fair_view(Knowledge(40, (R(70, None, False),), 8)).fair
    without = fair_view(Knowledge(40, (R(70, None, False),), 8, schedule=False)).fair
    assert with_rule > without + 5


# ── whole-game Monte Carlo (spec) ───────────────────────────────────────────

MC_CFG = OutcryConfig(players=6, rounds=5, makers=5, passives=0, anchors=0)  # extremes after rounds 2 and 3
MC_UNIVERSE = Universe(0, 8, 3, 6)
MC_GAMES = 60_000
MIN_GROUP = 300
SCENARIOS = {
    "own number only", "several reveals", "lowest revealed", "both extremes revealed", "your number revealed",
    "your number is the lowest",
}


def scenario(k: Knowledge) -> set[str]:
    tags = set()
    labels = {r.label for r in k.reveals}
    if not k.reveals:
        tags.add("own number only")
    if sum(1 for r in k.reveals if r.label is None and not r.mine) >= 2:
        tags.add("several reveals")
    if LOWEST in labels:
        tags.add("lowest revealed")
    if {LOWEST, HIGHEST} <= labels:
        tags.add("both extremes revealed")
    if any(r.mine for r in k.reveals):
        tags.add("your number revealed")
    if any(r.mine and r.label == LOWEST for r in k.reveals):
        tags.add("your number is the lowest")
    return tags


def test_fair_matches_whole_game_monte_carlo():
    """Two checks on one simulation. Every knowledge state seen often enough: its mean settle equals its
    fair. Every scenario from the spec: since fair = E[settle | knowledge], the residual settle − fair
    averages to 0 over the games in that scenario (one knowledge state per game, so they're independent)."""
    rng = random.Random(2024)
    groups = defaultdict(lambda: [0, 0, 0])
    residuals = defaultdict(list)
    for _ in range(MC_GAMES):
        s = draw_setup(MC_CFG, rng, MC_UNIVERSE)
        total = sum(s.numbers)
        tagged = set()
        for k in range(MC_CFG.rounds + 1):
            kn = knowledge_of(s, 0, k)
            g = groups[kn]
            g[0] += 1
            g[1] += total
            g[2] += total * total
            for tag in scenario(kn) - tagged:
                residuals[tag].append(total - fair_view(kn, MC_UNIVERSE).fair)
                tagged.add(tag)
    dense = 0
    for k, (n, s1, s2) in groups.items():
        if n < MIN_GROUP:
            continue
        mean = s1 / n
        se = math.sqrt(max(s2 / n - mean * mean, 1e-12) / (n - 1))
        assert fair_view(k, MC_UNIVERSE).fair == pytest.approx(mean, abs=5 * se), k
        dense += 1
    assert dense >= 30
    assert set(residuals) == SCENARIOS
    for tag, res in residuals.items():
        n = len(res)
        mean = sum(res) / n
        se = math.sqrt(sum((r - mean) ** 2 for r in res) / (n - 1) / n)
        assert n >= 1000 and abs(mean) <= 5 * se, (tag, n, mean, se)


def test_own_number_fair_matches_monte_carlo_in_the_real_range():
    rng = random.Random(7)
    groups = defaultdict(list)
    for _ in range(40_000):
        s = draw_setup(EASY, rng)
        groups[s.numbers[0]].append(sum(s.numbers))
    checked = 0
    for own, totals in groups.items():
        if len(totals) < 400:
            continue
        n = len(totals)
        mean = sum(totals) / n
        se = math.sqrt(sum((t - mean) ** 2 for t in totals) / (n - 1) / n)
        assert fair_view(Knowledge(own, (), 8)).fair == pytest.approx(mean, abs=5 * se)
        checked += 1
    assert checked >= 20


def test_posterior_bounds_contain_every_consistent_range():
    rng = random.Random(3)
    for _ in range(60):
        s = draw_setup(EASY, rng)
        for k in range(EASY.rounds + 1):
            view = fair_view(knowledge_of(s, 0, k))
            assert view.l_bounds[0] <= s.low <= view.l_bounds[1]
            assert view.u_bounds[0] <= s.high <= view.u_bounds[1]
            lo, hi = view.range_seen
            assert view.l_bounds[1] <= lo and view.u_bounds[0] >= hi


# ── reveal schedule ─────────────────────────────────────────────────────────


def test_extreme_rounds():
    assert extreme_rounds(7) == (2, 5)
    assert extreme_rounds(2) == (1, 2)
    assert extreme_rounds(4) == (1, 3)
    assert extreme_rounds(9) == (3, 6)


@pytest.mark.parametrize("preset", [EASY, MEDIUM, HARD])
def test_extremes_revealed_on_schedule_and_random_reveals_skip_them(preset):
    a, b = extreme_rounds(preset.rounds)
    orders = set()
    for seed in range(300):
        s = draw_setup(preset, random.Random(seed))
        labels = list(s.reveal_labels)
        assert {labels[a - 1], labels[b - 1]} == {LOWEST, HIGHEST}
        assert all(label is None for i, label in enumerate(labels) if i not in (a - 1, b - 1))
        lo_seat = s.reveal_order[labels.index(LOWEST)]
        hi_seat = s.reveal_order[labels.index(HIGHEST)]
        assert s.numbers[lo_seat] == min(s.numbers) and s.numbers[hi_seat] == max(s.numbers)
        assert lo_seat != hi_seat
        assert sorted(s.reveal_order) == list(range(preset.players))  # everyone revealed exactly once
        orders.add(labels[a - 1])
        assert (labels[a - 1] == LOWEST) == s.lowest_first
    assert orders == {LOWEST, HIGHEST}  # both orders occur


def test_ties_mark_one_copy_of_each_extreme():
    cfg = OutcryConfig(players=8)
    tied = 0
    for seed in range(400):
        s = draw_setup(cfg, random.Random(seed), Universe(0, 12, 3, 8))  # tiny range: ties are common
        labels = list(s.reveal_labels)
        assert labels.count(LOWEST) == labels.count(HIGHEST) == 1
        lo_seat = s.reveal_order[labels.index(LOWEST)]
        hi_seat = s.reveal_order[labels.index(HIGHEST)]
        assert s.numbers[lo_seat] == min(s.numbers) and s.numbers[hi_seat] == max(s.numbers)
        tied += s.numbers.count(min(s.numbers)) > 1 or s.numbers.count(max(s.numbers)) > 1
    assert tied > 100


def test_schedule_off_has_no_labels():
    s = draw_setup(EASY.replace(extreme_reveals=False), random.Random(1))
    assert set(s.reveal_labels) == {None} and sorted(s.reveal_order) == list(range(8))


def test_range_prior():
    pairs = range_pairs(0, 100, 10)
    assert len(pairs) == 91 * 92 // 2 and all(b - a >= 10 for a, b in pairs)
    for seed in range(200):
        s = draw_setup(EASY, random.Random(seed))
        assert 0 <= s.low < s.high <= 100 and s.high - s.low >= 10
        assert all(s.low <= v <= s.high for v in s.numbers)


def test_same_seed_same_setup():
    for preset in (EASY, MEDIUM, HARD):
        a, b = draw_setup(preset, random.Random(42)), draw_setup(preset, random.Random(42))
        assert a == b
        assert a != draw_setup(preset, random.Random(43))
        assert sorted(s for s in a.styles if s) == sorted(preset.style_list())


# ── config ───────────────────────────────────────────────────────────────────


def test_presets_match_table():
    assert (EASY.players, EASY.rounds, EASY.respond_s, EASY.outcry_s) == (8, 7, 15, 30)
    assert (MEDIUM.respond_s, MEDIUM.outcry_s, MEDIUM.helper) == (10, 20, "range")
    assert (HARD.respond_s, HARD.outcry_s, HARD.helper) == (5, 15, "off")
    assert not any(hasattr(p, "max_width") for p in (EASY, MEDIUM, HARD))  # no opening-width cap
    assert all((p.trade_size, p.limit) == (1, 10) for p in (EASY, MEDIUM, HARD))
    assert sorted(EASY.style_list()) == sorted(["PASSIVE"] * 3 + ["ANCHOR"] * 3 + ["MAKER"])
    assert sorted(MEDIUM.style_list()) == sorted(["MAKER", "MAKER", "SNIPER", "SNIPER", "PASSIVE", "CHASER", "ANCHOR"])
    assert sorted(HARD.style_list()) == sorted(["MAKER"] * 3 + ["SNIPER"] * 2 + ["CHASER", "ANCHOR"])
    assert (EASY.cooldown, MEDIUM.cooldown, HARD.cooldown) == ((6, 10), (3, 6), (1, 3))
    assert (EASY.pace_s, MEDIUM.pace_s, HARD.pace_s) == (1.5, 0.75, 0.25)
    assert all(p.report_s == 30 for p in (EASY, MEDIUM, HARD))
    assert (EASY.learns, MEDIUM.learns, HARD.learns) == (False, False, True)
    assert all(not p.errors() for p in (EASY, MEDIUM, HARD))


@pytest.mark.parametrize(
    "changes",
    [dict(players=3), dict(players=11), dict(rounds=8), dict(rounds=0), dict(trade_size=6), dict(limit=9),
     dict(limit=51), dict(helper="lots"), dict(makers=2), dict(cooldown_min=0.25), dict(cooldown_min=7, cooldown_max=6), dict(pace_s=0.3), dict(pace_s=0), dict(respond_s=1), dict(seed="x"),
     dict(rounds=1)],
)
def test_bad_configs_rejected(changes):
    assert EASY.replace(**changes).errors()


def test_custom_ranges_accepted_and_round_trip():
    cfg = EASY.replace(players=4, rounds=3, makers=1, passives=1, anchors=1, trade_size=5, limit=50)
    assert not cfg.errors()
    assert OutcryConfig.from_dict(HARD.to_dict()) == HARD
