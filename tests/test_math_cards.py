"""Card counting in the Probability drill (subtype cards_count): every answer recomputed by brute force — itertools
over a real 52-card deck for up to 3 cards, and one pass over all 2,598,960 five-card hands for the rest — never the
generator's formula. Plus whole-number input, the mistake detectors and the explanations."""

import random
from collections import Counter
from functools import cache
from itertools import combinations, permutations

import pytest

from met_games.games.math.config import PROB_DRILL, MathConfig
from met_games.games.math.prob import (
    CARDS,
    COUNT,
    KINDS,
    diagnose,
    is_right,
    make_level,
    make_prob,
    readable,
    whole_number,
)
from met_games.games.math.probdrill import ProbRun
from met_games.games.math.problems import EASY, HARD, MEDIUM

N = 3000  # card questions per difficulty
SUITS = ("heart", "diamond", "club", "spade")
DECK = [(r, s) for r in range(1, 14) for s in SUITS]  # rank 1 = ace


@cache
def five_card_counts() -> dict:
    """One pass over every 5-card hand. Cards are 0–51 with rank = c // 4 (0 = ace) and suit = c % 4 (0 = heart), so a
    hand drawn in index order has its ranks sorted. Rank- and suit-specific counts are taken for aces and hearts: by
    symmetry every rank / suit has the same counts."""
    shape, suits, aces = Counter(), Counter(), Counter()
    hearts_only = total = 0
    bits = [1 << (c % 4) for c in range(52)]
    for a, b, c, d, e in combinations(range(52), 5):
        total += 1
        r = (a >> 2, b >> 2, c >> 2, d >> 2, e >> 2)
        distinct = 1 + (r[0] != r[1]) + (r[1] != r[2]) + (r[2] != r[3]) + (r[3] != r[4])
        if distinct == 5:
            shape["distinct"] += 1
        elif distinct == 4:
            shape["one_pair"] += 1
        elif distinct == 3:
            trips = r[0] == r[2] or r[1] == r[3] or r[2] == r[4]
            shape["trips" if trips else "two_pair"] += 1
        else:
            quads = r[0] == r[3] or r[1] == r[4]
            shape["four_kind" if quads else "full_house"] += 1
        m = bits[a] | bits[b] | bits[c] | bits[d] | bits[e]
        suits[bin(m).count("1")] += 1
        hearts_only += m == 1
        aces[(a < 4) + (b < 4) + (c < 4) + (d < 4) + (e < 4)] += 1
    return {"total": total, "shape": shape, "suits": suits, "hearts_only": hearts_only, "aces": aces}


@pytest.fixture(scope="session")
def five():
    return five_card_counts()


def share_count(cards, n, keep):
    return sum(1 for h in combinations(cards, n) if keep(h))


@cache
def count_brute(operands) -> int:
    kind, *a = operands
    if kind == "hands":
        return five_card_counts()["total"] if a[0] == 5 else sum(1 for _ in combinations(DECK, a[0]))
    if kind == "ordered":
        return sum(1 for _ in permutations(DECK, a[0]))
    if kind == "both_suit":
        return share_count(DECK, 2, lambda h: all(c[1] == a[0] for c in h))
    if kind == "both_rank":
        return share_count(DECK, 2, lambda h: all(c[0] == a[0] for c in h))
    if kind == "one_each":
        return share_count(DECK, 2, lambda h: sorted(c[1] for c in h) == sorted(a))
    if kind == "exactly_rank":
        k, rank, want = a
        return share_count(DECK, k, lambda h: sum(c[0] == rank for c in h) == want)
    if kind == "same_suit":
        return share_count(DECK, a[0], lambda h: len({c[1] for c in h}) == 1)
    f = five_card_counts()
    if kind == "suit5":
        return f["hearts_only"] if a[0] is not None else f["suits"][1]
    if kind == "no_rank5":
        return f["aces"][0]
    if kind == "rank5_atleast":
        return f["total"] - f["aces"][0]
    if kind == "rank5_exactly":
        return f["aces"][a[1]]
    if kind == "two_suits":
        return f["suits"][2]
    if kind in ("four_kind", "full_house", "two_pair", "one_pair", "trips"):
        return f["shape"][kind]
    if kind == "distinct_ranks":
        return f["shape"]["distinct"]
    raise AssertionError(kind)


def test_the_published_five_card_counts(five):
    assert five["total"] == 2_598_960
    assert five["shape"]["four_kind"] == 624 and five["shape"]["full_house"] == 3_744
    assert five["suits"][1] == 5_148 and five["shape"]["trips"] == 54_912 and five["shape"]["two_pair"] == 123_552
    assert five["shape"]["one_pair"] == 1_098_240 and five["shape"]["distinct"] == 1_317_888
    assert five["total"] - five["aces"][0] == 886_656 and five["aces"][0] == 1_712_304
    assert five["suits"][2] == 379_236


def test_the_small_counts():
    assert count_brute(("hands", 2)) == 1_326 and count_brute(("ordered", 2)) == 2_652
    assert count_brute(("both_suit", "heart")) == 78 and count_brute(("both_rank", 1)) == 6
    assert count_brute(("one_each", "heart", "spade")) == 169 and count_brute(("ordered", 3)) == 132_600
    assert count_brute(("exactly_rank", 3, 1, 1)) == 4_512 and count_brute(("same_suit", 3)) == 1_144


@pytest.mark.parametrize("difficulty", [EASY, MEDIUM, HARD])
def test_thousands_of_card_questions_match_brute_force(difficulty, five):
    rng = random.Random(f"cards-{difficulty}")
    kinds = set()
    for _ in range(N):
        p = make_prob(rng, difficulty, CARDS)
        assert p.subtype == "cards_count" and p.form == COUNT
        assert p.answer.denominator == 1 and p.answer > 0 and p.answer == count_brute(p.operands), p.text
        assert p.text.startswith("How many") and ("order doesn't matter" in p.text or "order matters" in p.text)
        assert 2 <= len(p.explanation) <= 3 and p.answer_text in " ".join(p.explanation)
        kinds.add(p.operands[0].replace("_atleast", "").replace("_exactly", ""))
    expected = {"hands", "ordered", "both_suit", "both_rank", "one_each"} if difficulty == EASY else \
        {"hands", "ordered", "exactly_rank", "same_suit", "suit5", "no_rank5"} if difficulty == MEDIUM else \
        {"full_house", "four_kind", "two_pair", "one_pair", "trips", "rank5", "two_suits", "distinct_ranks"}
    assert kinds == expected


@pytest.mark.parametrize("level", range(1, 11))
def test_every_ladder_level_serves_counting_questions(level, five):
    rng = random.Random(f"cards-L{level}")
    for _ in range(300):
        p = make_level(rng, level, CARDS)
        assert p.answer == count_brute(p.operands) and p.level == f"L{level}"
    assert KINDS[level]["cards_count"]


def test_parameters_are_randomised():
    rng = random.Random(1)
    seen = {make_prob(rng, MEDIUM, CARDS).operands for _ in range(400)}
    assert {o[1] for o in seen if o[0] == "ordered"} == {2, 3} and {o[1] for o in seen if o[0] == "same_suit"} == {2, 3}
    assert len({o[2] for o in seen if o[0] == "exactly_rank"}) > 5  # which rank
    hard = {make_prob(rng, HARD, CARDS).operands for _ in range(800)}
    assert {o[0] for o in hard} >= {"rank5_atleast", "rank5_exactly"}


# ── input ───────────────────────────────────────────────────────────────────


def hands2():
    rng = random.Random(0)
    while True:
        p = make_prob(rng, EASY, CARDS)
        if p.operands == ("hands", 2):
            return p


def test_whole_numbers_only():
    p = hands2()
    assert p.answer == 1_326 and p.answer_text == "1,326"
    assert is_right(p, "1326") and is_right(p, "1,326") and is_right(p, " 1326 ")
    for text in ("1326.0", "1/1", "13,26", "1,3260", "", "-1326"):
        assert not readable(p, text) and not is_right(p, text), text
    assert readable(p, "1327") and not is_right(p, "1327")
    assert whole_number("2,598,960") == 2_598_960 and whole_number("2598960") == 2_598_960


def test_the_drill_takes_counts_and_ignores_anything_else():
    run = ProbRun(MathConfig(mode=PROB_DRILL, difficulty=EASY), 3)
    while run.problem.form != COUNT:
        run.skip()
    p = run.problem
    for text in ("1326.0", "1/1", ""):
        run.typed = text
        assert run.submit() is None and run.problem is p  # not a whole number: nothing happens
    run.typed = ""
    for ch in f"{p.answer.numerator:,}":
        run.type(ch)
    assert run.submit().correct
    while run.problem.form != COUNT:
        run.skip()
    run.typed = str(run.problem.answer.numerator + 1)
    a = run.submit()
    assert a.outcome == "wrong" and a.given == run.answers[-1].given
    s = run.skip()
    assert s.outcome == "skipped"


# ── mistakes ────────────────────────────────────────────────────────────────


def find(level, kind, rng_seed=0):
    rng = random.Random(rng_seed)
    for _ in range(20_000):
        p = make_level(rng, level, CARDS)
        if p.operands[0] == kind:
            return p
    raise AssertionError(kind)


FACT = {2: 2, 3: 6, 5: 120}


@pytest.mark.parametrize("level, kind, wrong, words", [
    (3, "hands", lambda p: p.answer * 2, "counts ordered draws"),
    (6, "hands", lambda p: p.answer * 120, "counts ordered draws"),
    (3, "both_suit", lambda p: p.answer * 2, "counts ordered draws"),
    (6, "same_suit", lambda p: p.answer * FACT[p.operands[1]], "counts ordered draws"),
    (9, "full_house", lambda p: p.answer * 120, "counts ordered draws"),
    (3, "ordered", lambda p: p.answer / 2, "counts hands"),
    (6, "ordered", lambda p: p.answer / FACT[p.operands[1]], "counts hands"),
    (9, "two_pair", lambda p: p.answer * 2, "C(13,2)"),
    (9, "rank5_atleast", lambda p: 4 * 249_900, "4 × C(51,4)"),
    (9, "one_pair", lambda p: 13 * 6 * 17_296, "3 different ranks"),
    (9, "trips", lambda p: p.answer + 3_744, "full houses"),
])
def test_each_detector_fires_on_its_exact_wrong_value_only(level, kind, wrong, words):
    p = find(level, kind)
    w = int(wrong(p))
    why = diagnose(p, str(w)) or ""
    assert words in why and "\n" not in why, (p.text, w, p.mistakes)
    assert diagnose(p, f"{w:,}") == why  # commas too
    assert diagnose(p, str(w + 1)) is None and diagnose(p, str(w - 1)) is None  # only the exact value
    assert diagnose(p, p.answer_text) is None and diagnose(p, str(p.answer.numerator)) is None


# ── explanations ────────────────────────────────────────────────────────────


def test_explanations_build_the_count_from_the_questions_numbers():
    assert find(9, "full_house").explanation[1] == "13 × C(4,3) × 12 × C(4,2) = 13 × 4 × 12 × 6 = 3,744"
    assert find(9, "rank5_atleast").explanation[1] == "C(52,5) − C(48,5) = 2,598,960 − 1,712,304 = 886,656"
    p = find(6, "exactly_rank")
    k = p.operands[1]
    assert f"C(48,{k - 1})" in p.explanation[1] and p.explanation[1].endswith(p.answer_text)
    p = find(9, "rank5_exactly")
    assert f"C(4,{p.operands[2]})" in p.explanation[1]
