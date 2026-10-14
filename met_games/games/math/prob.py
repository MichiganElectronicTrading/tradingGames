"""The probability family (`prob`, base 200): dice, cards, coins, expected value and (HARD) conditional probability.
Pure Python, exact Fractions, no Textual. Only the Probability drill uses it: it is never in FAMILIES, so it never
turns up in Sprint, Survival, Chain or the daily.

One ten-level ladder: L3 / L6 / L9 are EASY / MEDIUM / HARD.
- EASY: one die, one card, one coin flipped a few times, simple coin and card bets.
- MEDIUM: two dice, 2-card draws, up to 4 coins, the EV of a die.
- HARD: everything, including conditional probability, up to 6 coins, 3-card draws and pay-to-play games.

Every problem carries a 2–3 line explanation built from its own numbers, plus known wrong answers (with vs without
replacement, summing "at least one", a missing order count, an off-by-one dice sum) that `diagnose` recognises.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from fractions import Fraction
import re
from math import comb, perm
from typing import Any, Callable

from met_games.games.math.problems import EASY, FRACTION, HARD, MEDIUM, PROB, Problem, parse_answer

# cards_count (not "cards"): card questions are counting questions now; the old probability ones keep "cards" in
# history so the two never blend in the stats.
DICE, CARDS, COINS, EV, COND = "dice", "cards_count", "coins", "ev", "cond"
SUBTYPES = (DICE, CARDS, COINS, EV, COND)
SUBTYPE_LABELS = {DICE: "dice", CARDS: "card counting", COINS: "coins", EV: "expected value", COND: "conditional"}
LEVEL_MIN, LEVEL_MAX = 1, 10
ANCHORS = {3: EASY, 6: MEDIUM, 9: HARD}
ANCHOR_LEVEL = {v: k for k, v in ANCHORS.items()}

# The one tolerance in Mental Math: a decimal with ≥ 3 places within 0.0005 of the exact answer (see close_enough)
TOLERANCE = Fraction(5, 10_000)
MIN_PLACES = 3
COUNT = "count"  # a counting question's answer form: a whole number, commas allowed, no tolerance
_WHOLE = re.compile(r"(\d{1,3}(,\d{3})+|\d+)\Z")

RANK_NAMES = {1: "ace", 11: "jack", 12: "queen", 13: "king"}
SUITS = ("heart", "diamond", "club", "spade")


@dataclass(frozen=True)
class ProbProblem(Problem):
    explanation: tuple[str, ...] = ()
    mistakes: tuple[tuple[Fraction, str], ...] = ()  # (a known wrong answer, why it's wrong)

    @property
    def answer_text(self) -> str:
        return f"{self.answer.numerator:,}" if self.form == COUNT else fmt(self.answer)


def fmt(x: Fraction) -> str:
    """7/2, 6, -1/2 — reduced."""
    return str(Fraction(x))


# ── answers ─────────────────────────────────────────────────────────────────


def close_enough(exact: Fraction, text: str) -> bool:
    """THE tolerance. An exact fraction in any equivalent form, an exactly equal decimal ("0.75" for 3/4), or a
    decimal with at least 3 places within 0.0005 of the exact value."""
    text = text.strip()
    value = parse_answer(text)
    if value is None:
        return False
    if value == exact:
        return True
    if "/" in text or "." not in text:
        return False
    return len(text.split(".")[1]) >= MIN_PLACES and abs(value - exact) <= TOLERANCE


def whole_number(text: str) -> int | None:
    """A counting answer: digits, with commas between thousands allowed ("2,598,960"); anything else is None."""
    text = text.strip()
    return int(text.replace(",", "")) if _WHOLE.match(text) else None


def readable(problem: ProbProblem, text: str) -> bool:
    """Is this a well-formed answer for the problem (a whole number for counting; a number otherwise)?"""
    return whole_number(text) is not None if problem.form == COUNT else parse_answer(text.strip()) is not None


def matches(problem: ProbProblem, value: Fraction, text: str) -> bool:
    """`text` is `value`: exactly, as a whole number, for counting; within close_enough otherwise."""
    if problem.form == COUNT:
        typed = whole_number(text)
        return typed is not None and typed == value
    return close_enough(value, text)


def is_right(problem: ProbProblem, text: str) -> bool:
    return matches(problem, problem.answer, text)


def diagnose(problem: ProbProblem, text: str) -> str | None:
    """Why a wrong answer is wrong, when it is a known mistake (None for the right answer or an unknown one)."""
    if is_right(problem, text):
        return None
    return next((why for value, why in problem.mistakes if matches(problem, value, text)), None)


# ── words ───────────────────────────────────────────────────────────────────


def rank_name(r: int) -> str:
    return RANK_NAMES.get(r, str(r))


def article(word: str) -> str:
    return f"an {word}" if word[0] in "aeio8" or word in ("11",) else f"a {word}"


def what_count(what: tuple[Any, ...]) -> int:
    return {"rank": 4, "suit": 13, "face": 12, "red": 26}[what[0]]


def what_one(what: tuple[Any, ...]) -> str:
    """an ace · a heart · a face card · a red card."""
    kind = what[0]
    if kind == "rank":
        return article(rank_name(what[1]))
    if kind == "suit":
        return f"a {what[1]}"
    return "a face card" if kind == "face" else "a red card"


def what_many(what: tuple[Any, ...]) -> str:
    """aces · hearts · face cards · red cards."""
    kind = what[0]
    if kind == "rank":
        return f"{rank_name(what[1])}s"
    if kind == "suit":
        return f"{what[1]}s"
    return "face cards" if kind == "face" else "red cards"


def random_what(rng: random.Random, kinds: tuple[str, ...]) -> tuple[Any, ...]:
    kind = rng.choice(kinds)
    if kind == "rank":
        return ("rank", rng.randint(1, 13))
    if kind == "suit":
        return ("suit", rng.choice(SUITS))
    return (kind,)


def ways2(s: int) -> int:
    """Ordered pairs of two dice that sum to s."""
    return max(0, 6 - abs(s - 7))


def ways3(s: int) -> int:
    return sum(ways2(s - a) for a in range(1, 7))


def pairs_text(s: int) -> str:
    return " ".join(f"({a},{s - a})" for a in range(1, 7) if 1 <= s - a <= 6)


def no_run(n: int, r: int) -> int:
    """Sequences of n flips with no r heads in a row (by the number of heads they end on)."""
    ends = [1] + [0] * (r - 1)  # ends[j]: sequences ending in exactly j heads
    for _ in range(n):
        ends = [sum(ends)] + ends[:-1]
    return sum(ends)


@dataclass(frozen=True)
class Draft:
    text: str
    answer: Fraction
    subtype: str
    operands: tuple[Any, ...]
    explanation: tuple[str, ...]
    mistakes: tuple[tuple[Fraction, str], ...] = ()
    form: str = FRACTION


# ── dice ────────────────────────────────────────────────────────────────────


def die_eq(rng: random.Random, level: int) -> Draft:
    k = rng.randint(1, 6)
    return Draft(f"one die: P(rolling {article(str(k))})", Fraction(1, 6), DICE, ("die_eq", k),
                 (f"1 of the 6 faces is {article(str(k))}", "→ 1/6"))


def die_parity(rng: random.Random, level: int) -> Draft:
    even = rng.random() < 0.5
    faces = "2, 4, 6" if even else "1, 3, 5"
    return Draft(f"one die: P(an {'even' if even else 'odd'} number)", Fraction(1, 2), DICE,
                 ("die_parity", "even" if even else "odd"), (f"the {'even' if even else 'odd'} faces {faces}: 3 of 6",
                                                             "3/6 = 1/2"))


def die_ge(rng: random.Random, level: int) -> Draft:
    k = rng.randint(2, 5)
    ans = Fraction(7 - k, 6)
    return Draft(f"one die: P({k} or higher)", ans, DICE, ("die_ge", k),
                 (f"faces {k} to 6: {7 - k} of 6", f"{7 - k}/6 = {fmt(ans)}"),
                 ((Fraction(6 - k, 6), f"off by one: \"{k} or higher\" includes the {k} itself — {7 - k} faces"),))


def die_le(rng: random.Random, level: int) -> Draft:
    k = rng.randint(2, 5)
    ans = Fraction(k, 6)
    return Draft(f"one die: P({k} or lower)", ans, DICE, ("die_le", k),
                 (f"faces 1 to {k}: {k} of 6", f"{k}/6 = {fmt(ans)}"),
                 ((Fraction(k - 1, 6), f"off by one: \"{k} or lower\" includes the {k} itself — {k} faces"),))


def sum_mistakes(s: int, ways: Callable[[int], int], total: int, lo: int, hi: int) -> tuple[tuple[Fraction, str], ...]:
    return tuple((Fraction(ways(t), total), f"off by one: that's the count for a sum of {t} — recount the ways to "
                                            f"make {s}") for t in (s - 1, s + 1) if lo <= t <= hi)


def sum2(rng: random.Random, level: int) -> Draft:
    s = rng.randint(2, 12)
    w = ways2(s)
    ans = Fraction(w, 36)
    return Draft(f"two dice: P(the sum is {s})", ans, DICE, ("sum", 2, s),
                 (f"pairs that make {s}: {pairs_text(s)} = {w}", f"{w} of 36 → {w}/36 = {fmt(ans)}"),
                 sum_mistakes(s, ways2, 36, 2, 12))


def sum3(rng: random.Random, level: int) -> Draft:
    s = rng.randint(4, 17)
    w = ways3(s)
    ans = Fraction(w, 216)
    return Draft(f"three dice: P(the sum is {s})", ans, DICE, ("sum", 3, s),
                 (f"ways to make {s} with three dice: Σ over the first die of the two-dice ways = {w}",
                  f"{w} of 216 → {w}/216 = {fmt(ans)}"), sum_mistakes(s, ways3, 216, 3, 18))


def doubles(rng: random.Random, level: int) -> Draft:
    return Draft("two dice: P(doubles)", Fraction(1, 6), DICE, ("doubles",),
                 ("(1,1) (2,2) (3,3) (4,4) (5,5) (6,6): 6 of 36", "6/36 = 1/6"),
                 ((Fraction(1, 36), "that's one particular double — any of the 6 doubles counts"),))


AT_LEAST_N = {5: (2, 2), 6: (2, 2), 7: (2, 3), 8: (2, 3), 9: (2, 4), 10: (2, 6)}


def at_least(rng: random.Random, level: int) -> Draft:
    n, f = rng.randint(*AT_LEAST_N[level]), rng.randint(1, 6)
    none = Fraction(5**n, 6**n)
    ans = 1 - none
    return Draft(f"{n} rolls of a die: P(at least one {f})", ans, DICE, ("at_least", n, f),
                 (f"P(no {f}) = (5/6)^{n} = {5**n}/{6**n}", f"1 − {5**n}/{6**n} = {fmt(ans)}"),
                 ((Fraction(n, 6), f"adding 1/6 for each of the {n} rolls double-counts — use 1 − P(no {f})"),))


def max_eq(rng: random.Random, level: int) -> Draft:
    k = rng.randint(2, 6)
    ans = Fraction(2 * k - 1, 36)
    return Draft(f"two dice: P(the higher die shows {k})", ans, DICE, ("max_eq", k),
                 (f"both ≤ {k}: {k}×{k} = {k * k}; both ≤ {k - 1}: {(k - 1) ** 2}",
                  f"{k * k} − {(k - 1) ** 2} = {2 * k - 1} of 36 → {fmt(ans)}"),
                 ((Fraction(k * k, 36), f"that's P(both ≤ {k}) — take away the {(k - 1) ** 2} where both are below "
                                        f"{k}"),))


def min_eq(rng: random.Random, level: int) -> Draft:
    k = rng.randint(1, 5)
    ans = Fraction(13 - 2 * k, 36)
    return Draft(f"two dice: P(the lower die shows {k})", ans, DICE, ("min_eq", k),
                 (f"both ≥ {k}: {7 - k}×{7 - k} = {(7 - k) ** 2}; both ≥ {k + 1}: {(6 - k) ** 2}",
                  f"{(7 - k) ** 2} − {(6 - k) ** 2} = {13 - 2 * k} of 36 → {fmt(ans)}"),
                 ((Fraction((7 - k) ** 2, 36), f"that's P(both ≥ {k}) — take away the {(6 - k) ** 2} where both are "
                                              f"above {k}"),))


# ── cards: counting (combinatorics) ─────────────────────────────────────────
# Every card question asks for a whole number of ways, and says whether order matters ("as a hand" vs "in order").

HAND = "(order doesn't matter)"


def n(x: int) -> str:
    """2,598,960."""
    return f"{x:,}"


def plural_rank(r: int) -> str:
    return f"{rank_name(r)}s"


def ordered_mistake(ans: int, k: int) -> tuple[Fraction, str]:
    """A hand counted as ordered draws: × k!."""
    f = perm(k, k)
    return Fraction(ans * f), f"that counts ordered draws — a hand ignores order, so divide by {k}! = {f}"


def unordered_mistake(ans: int, k: int) -> tuple[Fraction, str]:
    """Ordered draws counted as hands: ÷ k!."""
    f = perm(k, k)
    return Fraction(ans // f), f"that counts hands — in order, every hand appears {k}! = {f} ways: multiply by {f}"


def count(text: str, ans: int, operands: tuple[Any, ...], explanation: tuple[str, ...],
          mistakes: tuple[tuple[Fraction, str], ...] = ()) -> Draft:
    return Draft(text, Fraction(ans), CARDS, operands, explanation, mistakes, COUNT)


def hands(rng: random.Random, level: int) -> Draft:
    k = 5 if level in (5, 6) else 2
    ans = comb(52, k)
    return count(f"How many different {k}-card hands {HAND} can be dealt from a 52-card deck?", ans, ("hands", k),
                 (f"C(52,{k}) = {n(ans)}", f"choose {k} of the 52 cards; order doesn't matter"),
                 (ordered_mistake(ans, k),))


def ordered(rng: random.Random, level: int) -> Draft:
    k = rng.choice((2, 3)) if level >= 5 else 2
    ans = perm(52, k)
    terms = " × ".join(str(52 - i) for i in range(k))
    return count(f"How many ordered draws of {k} cards (first, then second{', then third' if k == 3 else ''} — "
                 f"order matters) can be made from a 52-card deck?", ans, ("ordered", k),
                 (f"{terms} = {n(ans)}", f"order matters, so no ÷ {k}!"), (unordered_mistake(ans, k),))


def both_suit(rng: random.Random, level: int) -> Draft:
    suit = rng.choice(SUITS)
    ans = comb(13, 2)
    return count(f"How many 2-card hands {HAND} are both {suit}s?", ans, ("both_suit", suit),
                 (f"13 {suit}s, choose 2", f"C(13,2) = {n(ans)}"), (ordered_mistake(ans, 2),))


def both_rank(rng: random.Random, level: int) -> Draft:
    r = rng.randint(1, 13)
    ans = comb(4, 2)
    return count(f"How many 2-card hands {HAND} are both {plural_rank(r)}?", ans, ("both_rank", r),
                 (f"4 {plural_rank(r)}, choose 2", f"C(4,2) = {n(ans)}"), (ordered_mistake(ans, 2),))


def one_each(rng: random.Random, level: int) -> Draft:
    s1, s2 = rng.sample(SUITS, 2)
    ans = 13 * 13
    return count(f"How many 2-card hands {HAND} have one {s1} and one {s2}?", ans, ("one_each", s1, s2),
                 (f"13 {s1}s × 13 {s2}s", f"= {n(ans)}"), (ordered_mistake(ans, 2),))


def exactly_rank(rng: random.Random, level: int) -> Draft:
    k = rng.choice((2, 3)) if level >= 5 else 2
    r = rng.randint(1, 13)
    a, b = comb(4, 1), comb(48, k - 1)
    ans = a * b
    return count(f"How many {k}-card hands {HAND} contain exactly one {rank_name(r)}?", ans, ("exactly_rank", k, r, 1),
                 (f"one of the 4 {plural_rank(r)}, and {k - 1} of the 48 other cards",
                  f"C(4,1) × C(48,{k - 1}) = {a} × {n(b)} = {n(ans)}"), (ordered_mistake(ans, k),))


def same_suit(rng: random.Random, level: int) -> Draft:
    k = rng.choice((2, 3)) if level >= 5 else 2
    c = comb(13, k)
    ans = 4 * c
    return count(f"How many {k}-card hands {HAND} have all {k} cards the same suit?", ans, ("same_suit", k),
                 (f"pick the suit (4), then {k} of its 13 cards", f"4 × C(13,{k}) = 4 × {n(c)} = {n(ans)}"),
                 (ordered_mistake(ans, k),))


def suit5(rng: random.Random, level: int) -> Draft:
    c = comb(13, 5)
    if rng.random() < 0.5:
        suit = rng.choice(SUITS)
        return count(f"How many 5-card hands {HAND} are all {suit}s (straight flushes included)?", c,
                     ("suit5", suit), (f"5 of the 13 {suit}s", f"C(13,5) = {n(c)}"), (ordered_mistake(c, 5),))
    ans = 4 * c
    return count(f"How many 5-card hands {HAND} have all five cards the same suit (straight flushes included)?", ans,
                 ("suit5", None), ("pick the suit (4), then 5 of its 13 cards", f"4 × C(13,5) = 4 × {n(c)} = {n(ans)}"),
                 (ordered_mistake(ans, 5),))


def no_rank5(rng: random.Random, level: int) -> Draft:
    r = rng.randint(1, 13)
    ans = comb(48, 5)
    return count(f"How many 5-card hands {HAND} contain no {plural_rank(r)}?", ans, ("no_rank5", r),
                 (f"5 of the 48 cards that aren't {plural_rank(r)}", f"C(48,5) = {n(ans)}"), (ordered_mistake(ans, 5),))


def four_kind(rng: random.Random, level: int) -> Draft:
    ans = 13 * comb(4, 4) * 48
    return count(f"How many 5-card hands {HAND} have four cards of one rank (the fifth card is any other card)?", ans,
                 ("four_kind",), ("the rank (13), all 4 of it, then any of the 48 other cards",
                                  f"13 × C(4,4) × 48 = {n(ans)}"), (ordered_mistake(ans, 5),))


def full_house(rng: random.Random, level: int) -> Draft:
    ans = 13 * comb(4, 3) * 12 * comb(4, 2)
    return count(f"How many 5-card hands {HAND} have three cards of one rank and two cards of another rank?", ans,
                 ("full_house",), ("the triple's rank and 3 of its 4 suits; the pair's rank (12 left) and 2 of 4",
                                   f"13 × C(4,3) × 12 × C(4,2) = 13 × 4 × 12 × 6 = {n(ans)}"),
                 (ordered_mistake(ans, 5),))


def two_pair(rng: random.Random, level: int) -> Draft:
    ans = comb(13, 2) * comb(4, 2) ** 2 * 44
    return count(f"How many 5-card hands {HAND} have two cards of one rank, two cards of a second rank, and a fifth "
                 f"card of a third rank?", ans, ("two_pair",),
                 ("the two pair ranks C(13,2), 2 suits of each, then a fifth card from the 44 of other ranks",
                  f"C(13,2) × C(4,2)² × 44 = 78 × 36 × 44 = {n(ans)}"),
                 ((Fraction(2 * ans), "13 × 12 orders the two pair ranks, counting each hand twice — use C(13,2)"),
                  ordered_mistake(ans, 5)))


def one_pair(rng: random.Random, level: int) -> Draft:
    ans = 13 * comb(4, 2) * comb(12, 3) * 4**3
    loose = 13 * comb(4, 2) * comb(48, 3)
    return count(f"How many 5-card hands {HAND} have exactly two cards of one rank, and three cards of three other, "
                 f"different ranks?", ans, ("one_pair",),
                 ("the pair: 13 ranks × C(4,2); the other three: 3 of the 12 other ranks, any suit each",
                  f"13 × C(4,2) × C(12,3) × 4³ = 13 × 6 × 220 × 64 = {n(ans)}"),
                 ((Fraction(loose), "the 3 other cards must be 3 different ranks — C(12,3) × 4³, not C(48,3)"),
                  ordered_mistake(ans, 5)))


def trips(rng: random.Random, level: int) -> Draft:
    ans = 13 * comb(4, 3) * comb(12, 2) * 4**2
    loose = 13 * comb(4, 3) * comb(48, 2)
    return count(f"How many 5-card hands {HAND} have three cards of one rank and two cards of two other, different "
                 f"ranks (no full house)?", ans, ("trips",),
                 ("the triple: 13 ranks × C(4,3); the other two: 2 of the 12 other ranks, any suit each",
                  f"13 × C(4,3) × C(12,2) × 4² = 13 × 4 × 66 × 16 = {n(ans)}"),
                 ((Fraction(loose), "C(48,2) lets the other two cards pair up — that adds the 3,744 full houses"),
                  ordered_mistake(ans, 5)))


RANK5_K = {7: (1, 1), 8: (1, 1), 9: (1, 2), 10: (1, 3)}


def rank5(rng: random.Random, level: int) -> Draft:
    """At least one (or exactly k) of a rank in a 5-card hand."""
    r = rng.randint(1, 13)
    name, many = rank_name(r), plural_rank(r)
    if rng.random() < 0.5:
        total, none = comb(52, 5), comb(48, 5)
        ans = total - none
        return count(f"How many 5-card hands {HAND} contain at least one {name}?", ans, ("rank5_atleast", r),
                     (f"all hands minus those with no {many}",
                      f"C(52,5) − C(48,5) = {n(total)} − {n(none)} = {n(ans)}"),
                     ((Fraction(4 * comb(51, 4)), f"4 × C(51,4) counts hands with 2+ {many} more than once — use "
                                                  f"C(52,5) − C(48,5)"), ordered_mistake(ans, 5)))
    k = rng.randint(*RANK5_K[level])
    a, b = comb(4, k), comb(48, 5 - k)
    ans = a * b
    return count(f"How many 5-card hands {HAND} contain exactly {k} {name if k == 1 else many}?", ans,
                 ("rank5_exactly", r, k), (f"{k} of the 4 {many}, and {5 - k} of the 48 other cards",
                                          f"C(4,{k}) × C(48,{5 - k}) = {a} × {n(b)} = {n(ans)}"),
                 (ordered_mistake(ans, 5),))


def two_suits(rng: random.Random, level: int) -> Draft:
    pool, single = comb(26, 5), comb(13, 5)
    ans = comb(4, 2) * (pool - 2 * single)
    return count(f"How many 5-card hands {HAND} use exactly two suits (every card is one of two suits, and both "
                 f"appear)?", ans, ("two_suits",),
                 ("pick the 2 suits; take 5 of their 26 cards, minus the hands that use only one of them",
                  f"C(4,2) × (C(26,5) − 2 × C(13,5)) = 6 × ({n(pool)} − {n(2 * single)}) = {n(ans)}"),
                 (ordered_mistake(ans, 5),))


def distinct_ranks(rng: random.Random, level: int) -> Draft:
    c = comb(13, 5)
    ans = c * 4**5
    return count(f"How many 5-card hands {HAND} have five different ranks (straights and flushes included)?", ans,
                 ("distinct_ranks",), ("5 of the 13 ranks, then any of 4 suits for each card",
                                       f"C(13,5) × 4⁵ = {n(c)} × 1,024 = {n(ans)}"), (ordered_mistake(ans, 5),))


# ── coins ───────────────────────────────────────────────────────────────────

COIN_N = {1: (2, 2), 2: (2, 3), 3: (2, 3), 4: (2, 3), 5: (3, 4), 6: (3, 4), 7: (3, 5), 8: (3, 5), 9: (3, 6),
          10: (4, 8)}
RUN_N = {8: (4, 5), 9: (4, 6), 10: (5, 8)}
COND_COIN_N = {9: (2, 4), 10: (2, 6)}


def coins_all(rng: random.Random, level: int) -> Draft:
    n = rng.randint(*COIN_N[level])
    return Draft(f"{n} coin flips: P(all heads)", Fraction(1, 2**n), COINS, ("coins_all", n),
                 ("each flip is heads with probability 1/2", f"(1/2)^{n} = 1/{2**n}"))


def coins_exact(rng: random.Random, level: int) -> Draft:
    n = rng.randint(*COIN_N[level])
    k = rng.randint(1, n - 1)
    c = comb(n, k)
    ans = Fraction(c, 2**n)
    return Draft(f"{n} coin flips: P(exactly {k} heads)", ans, COINS, ("coins_exact", n, k),
                 (f"C({n},{k}) = {c} orders of {k} heads in {n} flips",
                  f"each order (1/2)^{n} = 1/{2**n} → {c}/{2**n} = {fmt(ans)}"),
                 ((Fraction(1, 2**n), f"that's one order — there are C({n},{k}) = {c} of them"),))


def coins_atleast(rng: random.Random, level: int) -> Draft:
    n = rng.randint(*COIN_N[level])
    ans = 1 - Fraction(1, 2**n)
    return Draft(f"{n} coin flips: P(at least one head)", ans, COINS, ("coins_atleast", n),
                 (f"P(no heads) = (1/2)^{n} = 1/{2**n}", f"1 − 1/{2**n} = {fmt(ans)}"),
                 ((Fraction(n, 2), f"adding 1/2 for each of the {n} flips double-counts — use 1 − P(no heads)"),))


def coins_run(rng: random.Random, level: int) -> Draft:
    n = rng.randint(*RUN_N[level])
    r = rng.randint(2, min(4, n - 1))
    no = no_run(n, r)
    ans = 1 - Fraction(no, 2**n)
    return Draft(f"{n} coin flips: P({r} or more heads in a row)", ans, COINS, ("coins_run", n, r),
                 (f"sequences of {n} flips with no {r} heads in a row: {no} of {2**n}",
                  f"1 − {no}/{2**n} = {fmt(ans)}"))


# ── expected value ──────────────────────────────────────────────────────────


def ev_coin(rng: random.Random, level: int) -> Draft:
    win, lose = rng.randint(2, 20), rng.randint(1, 20)
    ans = Fraction(win - lose, 2)
    return Draft(f"a coin: win ${win} on heads, lose ${lose} on tails. expected value", ans, EV,
                 ("ev_coin", win, lose), (f"½ × {win} − ½ × {lose}", f"= {fmt(ans)}"),
                 ((Fraction(win + lose, 2), f"the ${lose} is a loss — it counts negative"),))


def ev_card(rng: random.Random, level: int) -> Draft:
    win = rng.randint(5, 60)
    what = random_what(rng, ("rank", "suit", "face", "red"))
    c = what_count(what)
    ans = Fraction(win * c, 52)
    return Draft(f"one card from 52: win ${win} if it's {what_one(what)}. expected value", ans, EV,
                 ("ev_card", win, what), (f"P({what_one(what)}) = {c}/52", f"{win} × {c}/52 = {fmt(ans)}"))


def ev_die(rng: random.Random, level: int) -> Draft:
    return Draft("one die roll: expected value", Fraction(7, 2), EV, ("ev_die",),
                 ("(1 + 2 + 3 + 4 + 5 + 6) / 6 = 21/6", "= 7/2"))


def ev_die_mult(rng: random.Random, level: int) -> Draft:
    m = rng.randint(2, 9)
    ans = Fraction(7 * m, 2)
    return Draft(f"one die, paid ${m} × the face: expected payout", ans, EV, ("ev_die_mult", m),
                 ("E(face) = 21/6 = 7/2", f"{m} × 7/2 = {fmt(ans)}"))


def ev_die_sq(rng: random.Random, level: int) -> Draft:
    return Draft("one die, paid the face squared in $: expected payout", Fraction(91, 6), EV, ("ev_die_sq",),
                 ("(1 + 4 + 9 + 16 + 25 + 36) / 6", "= 91/6"),
                 ((Fraction(49, 4), "E(face²) isn't E(face)² = 49/4 — average the squares"),))


def ev_max2(rng: random.Random, level: int) -> Draft:
    return Draft("two dice: expected value of the higher one", Fraction(161, 36), EV, ("ev_max2",),
                 ("P(higher = k) = (2k − 1)/36", "Σ k(2k − 1)/36 = (1 + 6 + 15 + 28 + 45 + 66)/36 = 161/36"),
                 ((Fraction(7, 2), "that's one die — the higher of two averages more"),))


def ev_min2(rng: random.Random, level: int) -> Draft:
    return Draft("two dice: expected value of the lower one", Fraction(91, 36), EV, ("ev_min2",),
                 ("P(lower = k) = (13 − 2k)/36", "Σ k(13 − 2k)/36 = (11 + 18 + 21 + 20 + 15 + 6)/36 = 91/36"),
                 ((Fraction(7, 2), "that's one die — the lower of two averages less"),))


def ev_max3(rng: random.Random, level: int) -> Draft:
    return Draft("three dice: expected value of the highest", Fraction(119, 24), EV, ("ev_max3",),
                 ("P(highest = k) = (k³ − (k − 1)³)/216", "Σ k(k³ − (k − 1)³)/216 = 1071/216 = 119/24"),
                 ((Fraction(161, 36), "that's the higher of two dice — a third die pushes it up"),))


def ev_game_face(rng: random.Random, level: int) -> Draft:
    cost = rng.randint(2, 6)
    ans = Fraction(7, 2) - cost
    return Draft(f"pay ${cost} to roll a die; win the face in $. expected profit", ans, EV, ("ev_game_face", cost),
                 ("E(win) = 21/6 = 7/2", f"7/2 − {cost} = {fmt(ans)}"),
                 ((Fraction(7, 2), f"that's the expected win — take off the ${cost} it costs to play"),))


def ev_game_six(rng: random.Random, level: int) -> Draft:
    prize, cost = rng.randint(6, 30), rng.randint(1, 5)
    ans = Fraction(prize, 6) - cost
    return Draft(f"pay ${cost} to roll a die; win ${prize} on a 6. expected profit", ans, EV,
                 ("ev_game_six", cost, prize),
                 (f"E(win) = {prize} × 1/6 = {fmt(Fraction(prize, 6))}", f"{fmt(Fraction(prize, 6))} − {cost} = "
                                                                         f"{fmt(ans)}"),
                 ((Fraction(prize, 6), f"that's the expected win — take off the ${cost} it costs to play"),))


def fair_price(rng: random.Random, level: int) -> Draft:
    prize = rng.randint(10, 72)
    event = rng.choice((("sum", rng.randint(3, 11)), ("doubles",), ("a_six",)))
    if event[0] == "sum":
        p, words = Fraction(ways2(event[1]), 36), f"sum to {event[1]}"
    elif event[0] == "doubles":
        p, words = Fraction(1, 6), "show doubles"
    else:
        p, words = Fraction(11, 36), "show at least one 6"
    ans = prize * p
    return Draft(f"fair price to play: win ${prize} if two dice {words}", ans, EV, ("fair_price", prize, event),
                 (f"P(two dice {words}) = {fmt(p)}", f"fair price = {prize} × {fmt(p)} = {fmt(ans)}"))


# ── conditional (HARD) ──────────────────────────────────────────────────────


def cond_dice(rng: random.Random, level: int) -> Draft:
    f = rng.randint(1, 6)
    return Draft(f"two dice, at least one {f}: P(both {f}s)", Fraction(1, 11), COND, ("cond_dice", f),
                 (f"outcomes with at least one {f}: 36 − 25 = 11", f"only ({f},{f}) has both → 1/11"),
                 ((Fraction(1, 6), f"the other die isn't free — of the 11 outcomes with a {f}, one is double {f}"),
                  (Fraction(1, 36), f"that's unconditional — divide by P(at least one {f}) = 11/36")))


def cond_coins(rng: random.Random, level: int) -> Draft:
    n = rng.randint(*COND_COIN_N[level])
    ans = Fraction(1, 2**n - 1)
    return Draft(f"{n} coin flips, at least one head: P(all heads)", ans, COND, ("cond_coins", n),
                 (f"at least one head: 2^{n} − 1 = {2**n - 1} sequences", f"one of them is all heads → {fmt(ans)}"),
                 ((Fraction(1, 2**n), f"that's unconditional — only {2**n - 1} sequences are left"),
                  (Fraction(1, 2 ** (n - 1)), "fixing one flip as heads isn't \"at least one\"")))


def cond_cards(rng: random.Random, level: int) -> Draft:
    r = rng.randint(1, 13)
    name = rank_name(r)
    return Draft(f"2 cards from 52, at least one {name}: P(both {name}s)", Fraction(1, 33), COND, ("cond_cards", r),
                 (f"2-card hands: C(52,2) = 1326; with no {name}: C(48,2) = 1128; at least one: 198",
                  f"both {name}s: C(4,2) = 6 → 6/198 = 1/33"),
                 ((Fraction(1, 17), f"that's given the first card is {article(name)} — \"at least one\" is a bigger "
                                    f"set"),))


def cond_sum(rng: random.Random, level: int) -> Draft:
    while True:
        s, f = rng.randint(3, 11), rng.randint(1, 6)
        pairs = [(a, s - a) for a in range(1, 7) if 1 <= s - a <= 6]
        c = sum(f in p for p in pairs)
        if 0 < c < len(pairs):
            break
    ans = Fraction(c, len(pairs))
    return Draft(f"two dice sum to {s}: P(at least one shows {f})", ans, COND, ("cond_sum", s, f),
                 (f"pairs that make {s}: {pairs_text(s)} = {len(pairs)}",
                  f"{c} of them have a {f} → {c}/{len(pairs)} = {fmt(ans)}"),
                 ((Fraction(11, 36), f"that's unconditional — only the {len(pairs)} pairs making {s} are left"),))


KINDS: dict[int, dict[str, tuple[Callable[[random.Random, int], Draft], ...]]] = {
    1: {DICE: (die_eq, die_parity), CARDS: (both_rank, both_suit), COINS: (coins_all,), EV: (ev_coin,)},
    2: {DICE: (die_eq, die_parity, die_ge), CARDS: (both_rank, both_suit, one_each, hands), COINS: (coins_all,),
        EV: (ev_coin, ev_card)},
    3: {DICE: (die_eq, die_parity, die_ge, die_le), CARDS: (hands, ordered, both_suit, both_rank, one_each),
        COINS: (coins_all,), EV: (ev_coin, ev_card)},
    4: {DICE: (sum2, doubles, die_ge), CARDS: (hands, ordered, same_suit, exactly_rank),
        COINS: (coins_exact, coins_atleast), EV: (ev_die, ev_card)},
    5: {DICE: (sum2, doubles, at_least, max_eq), CARDS: (hands, ordered, same_suit, exactly_rank),
        COINS: (coins_exact, coins_atleast), EV: (ev_die, ev_die_mult)},
    6: {DICE: (sum2, doubles, at_least, max_eq, min_eq),
        CARDS: (hands, ordered, exactly_rank, same_suit, suit5, no_rank5),
        COINS: (coins_exact, coins_atleast), EV: (ev_die, ev_die_mult)},
    7: {DICE: (sum2, at_least, max_eq, min_eq), CARDS: (suit5, no_rank5, four_kind, distinct_ranks, rank5),
        COINS: (coins_exact, coins_atleast), EV: (ev_die_mult, ev_max2, ev_game_face, ev_game_six)},
    8: {DICE: (sum2, at_least, max_eq, min_eq), CARDS: (four_kind, full_house, distinct_ranks, rank5, trips),
        COINS: (coins_exact, coins_atleast, coins_run), EV: (ev_max2, ev_min2, ev_game_six, fair_price)},
    9: {DICE: (sum2, doubles, at_least, max_eq, min_eq),
        CARDS: (full_house, four_kind, two_pair, one_pair, trips, rank5, two_suits, distinct_ranks),
        COINS: (coins_exact, coins_atleast, coins_run),
        EV: (ev_die_sq, ev_max2, ev_min2, ev_game_face, ev_game_six, fair_price),
        COND: (cond_dice, cond_coins, cond_cards)},
    10: {DICE: (sum2, sum3, at_least, max_eq, min_eq),
         CARDS: (full_house, two_pair, one_pair, trips, rank5, two_suits, distinct_ranks),
         COINS: (coins_exact, coins_atleast, coins_run), EV: (ev_max2, ev_max3, ev_game_six, fair_price),
         COND: (cond_dice, cond_coins, cond_cards, cond_sum)},
}


def subtypes_at(level: int) -> tuple[str, ...]:
    return tuple(KINDS[level])


def make_level(rng: random.Random, level: int, subtype: str | None = None) -> ProbProblem:
    """A probability problem at ladder level 1–10 (its level reads "L<n>")."""
    if not LEVEL_MIN <= level <= LEVEL_MAX:
        raise ValueError(f"level must be {LEVEL_MIN}–{LEVEL_MAX}")
    kinds = KINDS[level]
    sub = subtype or rng.choice(tuple(kinds))
    d = rng.choice(kinds[sub])(rng, level)
    seen: set[Fraction] = set()
    mistakes = []
    for value, why in d.mistakes:  # a "mistake" that happens to equal the answer is no mistake
        if value != d.answer and value not in seen:
            seen.add(value)
            mistakes.append((value, why))
    return ProbProblem(d.text, d.answer, PROB, d.subtype, f"L{level}", "prob", d.operands, d.form,
                       explanation=d.explanation, mistakes=tuple(mistakes))


def make_prob(rng: random.Random, difficulty: str, subtype: str | None = None) -> ProbProblem:
    """EASY / MEDIUM / HARD: the ladder's L3 / L6 / L9, filed under the difficulty."""
    return replace(make_level(rng, ANCHOR_LEVEL[difficulty], subtype), level=difficulty)
