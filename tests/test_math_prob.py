"""The prob family: every answer recomputed by brute force (itertools over dice faces, coin sequences and a real
52-card deck) or exact EV sums — never the generator's formula — plus seeding, the one tolerance, the mistake
detectors, the explanations and the prob ladder. Card counting has its own file, test_math_cards."""

import random
import re
from fractions import Fraction as F
from functools import cache
from itertools import combinations, product

import pytest
from test_math_cards import count_brute

from met_games.games.math.ladder import ALL_TRACKS, PROB_TRACK, TRACKS, make_at
from met_games.games.math.prob import (
    CARDS,
    COINS,
    COND,
    DICE,
    EV,
    KINDS,
    ProbProblem,
    close_enough,
    diagnose,
    fmt,
    make_level,
    make_prob,
)
from met_games.games.math.problems import BASE, EASY, FAMILIES, HARD, MEDIUM, PROB

N = 400  # problems per difficulty
DIE = range(1, 7)
SUITS = ("heart", "diamond", "club", "spade")
DECK = [(r, s) for r in range(1, 14) for s in SUITS]


def is_(card, what):
    rank, suit = card
    kind = what[0]
    if kind == "rank":
        return rank == what[1]
    if kind == "suit":
        return suit == what[1]
    if kind == "face":
        return rank >= 11
    return suit in ("heart", "diamond")  # red


def share(outcomes, event):
    outcomes = list(outcomes)
    return F(sum(1 for o in outcomes if event(o)), len(outcomes))


def mean(outcomes, value):
    outcomes = list(outcomes)
    return F(sum(value(o) for o in outcomes), len(outcomes))


def given(outcomes, condition, event):
    kept = [o for o in outcomes if condition(o)]
    return F(sum(1 for o in kept if event(o)), len(kept))


@cache
def brute(operands):
    """The answer by enumerating every outcome."""
    kind, *a = operands
    dice = lambda n: product(DIE, repeat=n)  # noqa: E731
    flips = lambda n: ("".join(x) for x in product("HT", repeat=n))  # noqa: E731
    hands = lambda n: combinations(DECK, n)  # noqa: E731
    if kind == "die_eq":
        return share(DIE, lambda f: f == a[0])
    if kind == "die_parity":
        return share(DIE, lambda f: f % 2 == (0 if a[0] == "even" else 1))
    if kind == "die_ge":
        return share(DIE, lambda f: f >= a[0])
    if kind == "die_le":
        return share(DIE, lambda f: f <= a[0])
    if kind == "sum":
        return share(dice(a[0]), lambda o: sum(o) == a[1])
    if kind == "doubles":
        return share(dice(2), lambda o: o[0] == o[1])
    if kind == "at_least":
        return share(dice(a[0]), lambda o: a[1] in o)
    if kind == "max_eq":
        return share(dice(2), lambda o: max(o) == a[0])
    if kind == "min_eq":
        return share(dice(2), lambda o: min(o) == a[0])
    if kind == "coins_all":
        return share(flips(a[0]), lambda s: "T" not in s)
    if kind == "coins_exact":
        return share(flips(a[0]), lambda s: s.count("H") == a[1])
    if kind == "coins_atleast":
        return share(flips(a[0]), lambda s: "H" in s)
    if kind == "coins_run":
        return share(flips(a[0]), lambda s: "H" * a[1] in s)
    if kind == "ev_coin":
        return mean("HT", lambda x: a[0] if x == "H" else -a[1])
    if kind == "ev_card":
        return mean(DECK, lambda c: a[0] if is_(c, a[1]) else 0)
    if kind == "ev_die":
        return mean(DIE, lambda f: f)
    if kind == "ev_die_mult":
        return mean(DIE, lambda f: a[0] * f)
    if kind == "ev_die_sq":
        return mean(DIE, lambda f: f * f)
    if kind == "ev_max2":
        return mean(dice(2), max)
    if kind == "ev_min2":
        return mean(dice(2), min)
    if kind == "ev_max3":
        return mean(dice(3), max)
    if kind == "ev_game_face":
        return mean(DIE, lambda f: f - a[0])
    if kind == "ev_game_six":
        return mean(DIE, lambda f: (a[1] if f == 6 else 0) - a[0])
    if kind == "fair_price":
        prize, event = a
        wins = {"sum": lambda o: sum(o) == event[-1], "doubles": lambda o: o[0] == o[1],
                "a_six": lambda o: 6 in o}[event[0]]
        return mean(dice(2), lambda o: prize if wins(o) else 0)
    if kind == "cond_dice":
        return given(dice(2), lambda o: a[0] in o, lambda o: o == (a[0], a[0]))
    if kind == "cond_coins":
        return given(flips(a[0]), lambda s: "H" in s, lambda s: "T" not in s)
    if kind == "cond_cards":
        return given(hands(2), lambda h: any(c[0] == a[0] for c in h), lambda h: all(c[0] == a[0] for c in h))
    if kind == "cond_sum":
        return given(dice(2), lambda o: sum(o) == a[0], lambda o: a[1] in o)
    raise AssertionError(kind)


def check(p: ProbProblem):
    expected = count_brute(p.operands) if p.subtype == CARDS else brute(p.operands)  # counting: test_math_cards
    assert isinstance(p.answer, F) and p.answer == expected, (p.text, p.operands)
    assert p.family == PROB and p.base == 200 and p.tip_key == "prob"
    assert 2 <= len(p.explanation) <= 3
    assert all(v != p.answer for v, _ in p.mistakes)


@pytest.mark.parametrize("difficulty", [EASY, MEDIUM, HARD])
def test_every_subtype_by_brute_force(difficulty):
    rng = random.Random(f"prob-{difficulty}")
    seen = set()
    for _ in range(N):
        p = make_prob(rng, difficulty)
        check(p)
        assert p.level == difficulty
        seen.add(p.subtype)
    assert seen == ({DICE, CARDS, COINS, EV, COND} if difficulty == HARD else {DICE, CARDS, COINS, EV})


@pytest.mark.parametrize("level", range(1, 11))
def test_every_ladder_level_by_brute_force(level):
    rng = random.Random(f"prob-L{level}")
    kinds = set()
    for _ in range(N):
        p = make_level(rng, level)
        check(p)
        assert p.level == f"L{level}"
        kinds.add(re.sub(r"_(atleast|exactly)$", "", p.operands[0]) if p.subtype == CARDS else p.operands[0])
    expected = {f.__name__ for fs in KINDS[level].values() for f in fs}
    expected = {"sum" if k in ("sum2", "sum3") else k for k in expected}
    assert kinds == expected


def test_difficulty_contents():
    def kinds(diff):
        rng = random.Random(diff)
        return {make_prob(rng, diff).operands for _ in range(N)}

    easy, medium, hard = kinds(EASY), kinds(MEDIUM), kinds(HARD)
    assert all(o[0] in ("die_eq", "die_parity", "die_ge", "die_le", "coins_all", "ev_coin", "ev_card", "hands",
                        "ordered", "both_suit", "both_rank", "one_each") for o in easy)
    assert {o[0] for o in medium} >= {"sum", "hands", "ordered", "same_suit", "coins_exact", "ev_die"}
    assert max(o[1] for o in medium if o[0].startswith("coins")) <= 4
    assert {o[0] for o in hard} >= {"cond_dice", "cond_coins", "cond_cards", "trips", "coins_run", "ev_game_six",
                                    "fair_price", "full_house"}
    assert max(o[1] for o in hard if o[0].startswith("coins")) == 6


def test_same_seed_same_problems():
    a = [make_prob(random.Random(9), MEDIUM) for _ in range(1)]
    r1, r2 = random.Random(5), random.Random(5)
    assert [make_prob(r1, HARD) for _ in range(50)] == [make_prob(r2, HARD) for _ in range(50)]
    assert a == [make_prob(random.Random(9), MEDIUM)]


def test_the_prob_ladder_is_an_adaptive_track_but_never_a_sprint_family():
    assert PROB not in FAMILIES and BASE[PROB] == 200
    assert PROB_TRACK in ALL_TRACKS and PROB_TRACK not in TRACKS
    for seed in range(20):
        for level, diff in ((3, EASY), (6, MEDIUM), (9, HARD)):
            ours = make_at(random.Random(seed), PROB_TRACK, level)
            theirs = make_prob(random.Random(seed), diff)
            assert ours.text == theirs.text and ours.answer == theirs.answer and ours.level == f"L{level}"


# ── the tolerance ───────────────────────────────────────────────────────────


def test_exact_and_equivalent_fractions():
    assert close_enough(F(1, 6), "1/6") and close_enough(F(1, 6), "2/12") and close_enough(F(1, 6), " 3/18 ")
    assert not close_enough(F(1, 6), "1/7") and not close_enough(F(1, 6), "")
    assert close_enough(F(-1, 2), "-1/2") and close_enough(F(-1, 2), "-0.5") and close_enough(F(7), "7")


def test_three_place_decimals_within_half_a_thousandth():
    third = F(1, 6)  # 0.16666…
    assert close_enough(third, "0.167") and close_enough(third, ".167") and close_enough(third, "0.1667")
    assert not close_enough(third, "0.168") and not close_enough(third, "0.166")  # 0.00133 and 0.00067 off
    assert close_enough(F(3, 4), "0.7505") and not close_enough(F(3, 4), "0.7506")  # 0.0005 is in, just over is out
    assert close_enough(F(161, 36), "4.472")


def test_two_place_decimals_only_when_exactly_equal():
    assert close_enough(F(3, 4), "0.75") and close_enough(F(1, 2), "0.5") and close_enough(F(3, 4), "0.750")
    assert not close_enough(F(1, 6), "0.17") and not close_enough(F(1, 3), "0.33")


# ── mistakes ────────────────────────────────────────────────────────────────


def find(level, kind, **want):
    rng = random.Random(f"find-{kind}")
    for _ in range(5000):
        p = make_level(rng, level)
        if p.operands[0] == kind and all(p.operands[int(k[1:])] == v for k, v in want.items()):
            return p
    raise AssertionError(kind)


@pytest.mark.parametrize("level, kind, wrong, words", [
    (6, "at_least", lambda p: F(p.operands[1], 6), "1 − P(no"),
    (6, "coins_atleast", lambda p: F(p.operands[1], 2), "1 − P(no heads)"),
    (6, "coins_exact", lambda p: F(1, 2 ** p.operands[1]), "one order"),
    (6, "sum", lambda p: F(6 - abs(p.operands[2] + 1 - 7), 36) if p.operands[2] < 12 else None, "off by one"),
])
def test_each_mistake_detector_fires_on_its_wrong_answer_only(level, kind, wrong, words):
    rng = random.Random(kind)
    hits = 0
    for _ in range(3000):
        p = make_level(rng, level)
        if p.operands[0] != kind:
            continue
        w = wrong(p)
        if w is None or w == p.answer:
            continue
        assert words in (diagnose(p, fmt(w)) or ""), (p.text, fmt(w), p.mistakes)
        assert diagnose(p, p.answer_text) is None
        hits += 1
    assert hits >= 5


def test_a_mistake_typed_as_a_decimal_is_recognised_too():
    p = find(6, "at_least")  # two rolls
    assert p.answer == F(11, 36) and "1 − P(no" in diagnose(p, "0.333")  # summed: 2/6
    assert diagnose(p, "0.306") is None  # right (11/36 = 0.3055…)
    assert diagnose(p, "0.9") is None  # wrong, but no known mistake


# ── explanations ────────────────────────────────────────────────────────────


def test_explanations_use_the_problems_own_numbers():
    p = find(6, "at_least")
    assert p.explanation == (f"P(no {p.operands[2]}) = (5/6)^2 = 25/36", "1 − 25/36 = 11/36")
    for level in range(1, 11):
        rng = random.Random(f"why-{level}")
        for _ in range(200):
            p = make_level(rng, level)
            why = " ".join(p.explanation)
            assert p.answer_text in why, (p.text, why)
            setup = re.sub(r"^\d cards|\d+-card", "", p.text)  # not the hand size
            numbers = set(re.findall(r"\d+", setup)) - {"52"}
            if numbers:
                assert numbers & set(re.findall(r"\d+", why)), (p.text, why)
