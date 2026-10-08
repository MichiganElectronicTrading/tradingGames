"""Outcry number model: the hidden range, the deal, the reveal schedule, and exact fair value.

Pure Python, no UI imports.

The hidden range (L, U) is uniform over integer pairs lo ≤ L < U ≤ hi with U − L ≥ min_width, and every
player's number is an independent uniform integer in [L, U]. The contract settles at the sum of all of them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from math import comb

from mtt_games.games.outcry.config import OutcryConfig

LOWEST, HIGHEST = "LOWEST", "HIGHEST"


@dataclass(frozen=True)
class Universe:
    """The prior over the hidden range. The game uses 0–100 with U − L ≥ 10; tests shrink it."""

    lo: int = 0
    hi: int = 100
    min_width: int = 10
    players: int = 8


@lru_cache(maxsize=None)
def range_pairs(lo: int, hi: int, min_width: int) -> tuple[tuple[int, int], ...]:
    return tuple((a, b) for a in range(lo, hi + 1) for b in range(a + min_width, hi + 1))


def extreme_rounds(rounds: int) -> tuple[int, int]:
    """Rounds after which the two extremes are revealed: round(R/3) and round(2R/3), kept distinct and ≥ 1."""
    first = max(1, round(rounds / 3))
    return first, max(first + 1, round(2 * rounds / 3))


# ── setup ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Setup:
    """Everything drawn at the start of a game. Private: it knows who owns every number."""

    low: int  # L
    high: int  # U
    numbers: tuple[int, ...]  # by seat (seat 0 = you)
    styles: tuple[str | None, ...]  # by seat; None for you
    openers: tuple[int, ...]  # seat forced to open, per round
    response_orders: tuple[tuple[int, ...], ...]  # order forced responses are applied in, per round
    reveal_order: tuple[int, ...]  # seats in reveal order: one per round, then the final reveal(s)
    reveal_labels: tuple[str | None, ...]  # LOWEST / HIGHEST / None, parallel to reveal_order
    lowest_first: bool  # False when the 50/50 draw swapped the extremes
    trader_seeds: tuple[int, ...]  # seeds for each trader's own RNG, by seat (0 for you)


def draw_setup(cfg: OutcryConfig, rng: random.Random, universe: Universe | None = None) -> Setup:
    """Draw order: range, numbers, styles, openers, response orders, extreme copies + swap, reveals,
    trader seeds."""
    u = universe or Universe(players=cfg.players)
    n, rounds = cfg.players, cfg.rounds
    low, high = rng.choice(range_pairs(u.lo, u.hi, u.min_width))
    numbers = tuple(rng.randint(low, high) for _ in range(n))
    styles = cfg.style_list()
    rng.shuffle(styles)
    openers = tuple(rng.randrange(n) for _ in range(rounds))
    response_orders = tuple(tuple(rng.sample(range(n), n)) for _ in range(rounds))

    order: list[int] = []
    labels: list[str | None] = []
    lowest_first = True
    if cfg.extreme_reveals:
        lo_seat = rng.choice([i for i in range(n) if numbers[i] == min(numbers)])
        hi_seat = rng.choice([i for i in range(n) if numbers[i] == max(numbers) and i != lo_seat])
        lowest_first = rng.random() >= 0.5
        a, b = extreme_rounds(rounds)
        firsts = [(lo_seat, LOWEST), (hi_seat, HIGHEST)]
        if not lowest_first:
            firsts.reverse()
        hidden = [i for i in range(n) if i not in (lo_seat, hi_seat)]
        for r in range(1, rounds + 1):
            if r in (a, b):
                seat, label = firsts[0 if r == a else 1]
            else:
                seat, label = rng.choice(hidden), None
                hidden.remove(seat)
            order.append(seat)
            labels.append(label)
        rng.shuffle(hidden)
        order += hidden
        labels += [None] * len(hidden)
    else:
        order = rng.sample(range(n), n)
        labels = [None] * n
    seeds = tuple(0 if i == 0 else rng.getrandbits(64) for i in range(n))
    return Setup(
        low=low, high=high, numbers=numbers, styles=(None, *styles), openers=openers,
        response_orders=response_orders, reveal_order=tuple(order), reveal_labels=tuple(labels),
        lowest_first=lowest_first, trader_seeds=seeds,
    )


# ── knowledge + exact fair ───────────────────────────────────────────────────


@dataclass(frozen=True)
class SeenReveal:
    """One reveal as a particular player saw it."""

    value: int
    label: str | None  # LOWEST / HIGHEST / None
    mine: bool  # was it this player's own number?


@dataclass(frozen=True)
class Knowledge:
    """What one player knows: their own number, every reveal so far (in order), and the game's rules."""

    own: int
    reveals: tuple[SeenReveal, ...]
    players: int
    schedule: bool = True  # extremes revealed on schedule (so unlabeled reveals are never an extreme)

    @property
    def known(self) -> list[int]:
        """Values whose owners are pinned down: your own number plus every reveal that wasn't yours."""
        return [self.own] + [r.value for r in self.reveals if not r.mine]

    @property
    def unknown(self) -> int:
        return self.players - len(self.known)

    def labeled(self, label: str) -> int | None:
        return next((r.value for r in self.reveals if r.label == label), None)

    @property
    def range_seen(self) -> tuple[int, int]:
        known = self.known
        return min(known), max(known)

    def seats(self) -> tuple[tuple[int, bool, str | None], ...]:
        """Known seats as (value, still eligible to be an unrevealed extreme, LOWEST/HIGHEST role)."""
        mine = next((r for r in self.reveals if r.mine), None)
        me = (self.own, mine is None, mine.label if mine else None)
        return (me, *((r.value, False, r.label) for r in self.reveals if not r.mine))


def knowledge_of(setup: Setup, seat: int, revealed: int, schedule: bool = True) -> Knowledge:
    """`seat`'s knowledge after the first `revealed` reveals."""
    reveals = tuple(
        SeenReveal(setup.numbers[s], label, s == seat)
        for s, label in zip(setup.reveal_order[:revealed], setup.reveal_labels[:revealed])
    )
    return Knowledge(setup.numbers[seat], reveals, len(setup.numbers), schedule)


@dataclass(frozen=True)
class FairView:
    fair: float  # E[sum of all numbers | knowledge]
    l_bounds: tuple[int, int]  # smallest and largest L with nonzero posterior weight
    u_bounds: tuple[int, int]  # same for U
    range_seen: tuple[int, int]  # [smallest known value, largest known value]


def fair_view(k: Knowledge, universe: Universe | None = None) -> FairView:
    u = universe or Universe(players=k.players)
    fair, l_bounds, u_bounds = _fair(k.seats(), k.unknown, k.schedule, u.lo, u.hi, u.min_width)
    return FairView(fair, l_bounds, u_bounds, k.range_seen)


@lru_cache(maxsize=None)
def _range_weights(lo: int, hi: int, min_width: int, n: int) -> list[list[float]]:
    """phi[p][q] = Σ over allowed (L, U) with L ≤ p and U ≥ q of (U − L + 1)^−n (indices offset by lo)."""
    size = hi - lo + 1
    suffix = [[0.0] * (size + 1) for _ in range(size)]  # suffix[L][U] = Σ_{U' ≥ U} w(L, U')
    for a in range(size):
        for b in range(size - 1, -1, -1):
            w = (b - a + 1) ** -n if b - a >= min_width else 0.0
            suffix[a][b] = suffix[a][b + 1] + w
    phi = [[0.0] * size for _ in range(size)]
    for q in range(size):
        running = 0.0
        for p in range(size):
            running += suffix[p][max(q, p + min_width)] if p + min_width < size else 0.0
            phi[p][q] = running
    return phi


def _count_max(n: int, a: int, b: int) -> tuple[int, int]:
    """(configs, Σ of value-sums over them) for n iid values in [a, b] whose max is exactly b."""
    full, short = b - a + 1, b - a
    count = full**n - short**n
    total = n * (full ** (n - 1) * (a + b) * full // 2 - (short ** (n - 1) * (a + b - 1) * short // 2 if short else 0))
    return count, total


def _count_min(n: int, a: int, b: int) -> tuple[int, int]:
    """(configs, Σ of value-sums) for n iid values in [a, b] whose min is exactly a."""
    full, short = b - a + 1, b - a
    count = full**n - short**n
    total = n * (full ** (n - 1) * (a + b) * full // 2 - (short ** (n - 1) * (a + 1 + b) * short // 2 if short else 0))
    return count, total


@lru_cache(maxsize=8192)
def _fair(
    seats: tuple[tuple[int, bool, str | None], ...], unknown: int, schedule: bool, lo: int, hi: int, min_width: int,
) -> tuple[float, tuple[int, int], tuple[int, int]]:
    """Exact E[sum | knowledge] under the game's own process.

    Weight of a hidden range (L, U) and a configuration of the unknown numbers =
        (U − L + 1)^−N · [every value in [L, U]] · P(the reveal rule produced what was seen).
    With the extreme schedule on, that last factor is the probability that the marked lowest/highest
    copies are the ones revealed as LOWEST/HIGHEST, and that neither is among the unlabeled reveals.
    Ties are broken uniformly at random, so it is a ratio of counts at the global min and max. The
    unknowns are summed by their min s and max t (closed-form counts), and the (L, U) prior by a
    2-D cumulative table, so nothing here is sampled.
    """
    n = len(seats) + unknown
    values = [v for v, _, _ in seats]
    kmin, kmax, ksum = min(values), max(values), sum(values)
    lowest = next((v for v, _, role in seats if role == LOWEST), None)
    highest = next((v for v, _, role in seats if role == HIGHEST), None)

    def count(v: int) -> int:
        return sum(1 for x, _, _ in seats if x == v)

    def eligible(v: int) -> int:
        return sum(1 for x, e, _ in seats if x == v and e)

    def mark(g: int, cug: int, top: int, cut: int) -> float:
        """P(marking consistent | global min g with cug unknown copies, global max top with cut copies)."""
        if not schedule:
            return 1.0
        cg, eg = cug + count(g), cug + eligible(g)
        if g < top:
            p_low = (1.0 / cg if g == lowest else 0.0) if lowest is not None else eg / cg
            ct, et = cut + count(top), cut + eligible(top)
            p_high = (1.0 / ct if top == highest else 0.0) if highest is not None else et / ct
            return p_low * p_high
        # all n values equal: the lowest copy is uniform over n seats, the highest over the other n − 1
        if lowest is not None and highest is not None:
            return 1.0 / (n * (n - 1))
        if lowest is not None or highest is not None:
            return eg / (n * (n - 1))
        return eg * (eg - 1) / (n * (n - 1))

    phi = _range_weights(lo, hi, min_width, n)
    num = den = 0.0
    max_p, min_q = lo - 1, hi + 1
    s_lo = lo if lowest is None else lowest
    t_hi = hi if highest is None else highest

    def add(p: int, q: int, weight: float, total: float) -> None:
        nonlocal num, den, max_p, min_q
        if weight <= 0:
            return
        f = phi[p - lo][q - lo]
        if f <= 0:
            return
        num += f * total
        den += f * weight
        max_p, min_q = max(max_p, p), min(min_q, q)

    if unknown == 0:
        add(kmin, kmax, mark(kmin, 0, kmax, 0), 0.0)
    else:
        u = unknown
        pw = [d**u for d in range(hi - lo + 3)]
        for s in range(s_lo, t_hi + 1):
            for t in range(s, t_hi + 1):
                p, q = min(s, kmin), max(t, kmax)
                if s == t:  # every unknown equals s
                    f = mark(p, u if s == p else 0, q, u if s == q else 0)
                    add(p, q, f, f * u * s)
                    continue
                d = t - s
                dep_low, dep_high = s == kmin, t == kmax  # only then do the tie counts matter
                if not dep_low and not dep_high:
                    f = mark(p, 1 if s < kmin else 0, q, 1 if t > kmax else 0)
                    if f:
                        configs = pw[d + 1] - 2 * pw[d] + pw[d - 1]
                        add(p, q, f * configs, f * configs * u * (s + t) / 2)
                elif dep_low and not dep_high:
                    for i in range(1, u):
                        f = mark(s, i, q, 1 if t > kmax else 0)
                        if f:
                            c, tot = _count_max(u - i, s + 1, t)
                            ways = comb(u, i)
                            add(p, q, f * ways * c, f * ways * (i * s * c + tot))
                elif dep_high and not dep_low:
                    for j in range(1, u):
                        f = mark(p, 1 if s < kmin else 0, t, j)
                        if f:
                            c, tot = _count_min(u - j, s, t - 1)
                            ways = comb(u, j)
                            add(p, q, f * ways * c, f * ways * (j * t * c + tot))
                else:
                    for i in range(1, u):
                        for j in range(1, u - i + 1):
                            f = mark(s, i, t, j)
                            if f:
                                r = u - i - j
                                ways = comb(u, i) * comb(u - i, j) * (d - 1) ** r
                                add(p, q, f * ways, f * ways * (i * s + j * t + r * (s + t) / 2))
    if den == 0:
        raise ValueError("knowledge is impossible under the prior")
    l_bounds = (lo, min(max_p, hi - min_width))
    u_bounds = (max(min_q, lo + min_width), hi)
    return ksum + num / den, l_bounds, u_bounds
