"""Higher or Lower: decks, the Kelly bet, grading and scoring. Pure Python, exact arithmetic (Fraction).

Ranks run A = 1 … K = 13. Bets are even money; the right (Kelly) stake on a two-outcome even-money bet
with h winning and l losing cards (ties excluded) is k = |h − l| / (h + l) on the side with more cards.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from fractions import Fraction

from met_games.games.hilo.config import FULL, INTERVIEW, REDBLACK

SUITS = ("♠", "♥", "♦", "♣")
RED_SUITS = frozenset({"♥", "♦"})
LABELS = {1: "A", 11: "J", 12: "Q", 13: "K"}

HIGHER, LOWER, RED, BLACK = "HIGHER", "LOWER", "RED", "BLACK"
PERFECT, GOOD, OK, DISCIPLINE, MISS, SAT_OUT = "PERFECT", "GOOD", "OK", "DISCIPLINE", "MISS", "SAT OUT"
BASE = {PERFECT: 100, GOOD: 60, OK: 20, DISCIPLINE: 50, MISS: 0, SAT_OUT: 0}
STREAK_GRADES = frozenset({PERFECT, GOOD, DISCIPLINE})  # build the combo (and earn speed)
LIGHTNING, FAST, NORMAL = "LIGHTNING", "FAST", "NORMAL"
SPEED = {LIGHTNING: Fraction(2), FAST: Fraction(3, 2), NORMAL: Fraction(1)}
COMBO_STEP, COMBO_CAP = Fraction(1, 10), Fraction(3)


@dataclass(frozen=True)
class Card:
    rank: int  # 1..13
    suit: str

    @property
    def label(self) -> str:
        return LABELS.get(self.rank, str(self.rank))

    @property
    def red(self) -> bool:
        return self.suit in RED_SUITS

    def __str__(self) -> str:
        return f"{self.label}{self.suit}"


# ── decks ────────────────────────────────────────────────────────────────────


def build_deck(kind: str, rng: random.Random) -> list[Card]:
    """The shuffled deck. Interview: A–K once each (each with a random suit). Full / Red-Black: 52 cards.
    Everything comes from `rng`, so the seed alone fixes the order."""
    if kind == INTERVIEW:
        cards = [Card(r, rng.choice(SUITS)) for r in range(1, 14)]
    elif kind in (FULL, REDBLACK):
        cards = [Card(r, s) for s in SUITS for r in range(1, 14)]
    else:
        raise ValueError(f"unknown deck {kind!r}")
    rng.shuffle(cards)
    return cards


def bets_in(kind: str, cards: int) -> int:
    """Interview / Full: one bet per card after the first. Red/Black: every card is bet on."""
    return cards if kind == REDBLACK else cards - 1


# ── the right bet ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Odds:
    h: int  # cards left that win HIGHER (or RED)
    same: int  # same rank as the showing card (a push); always 0 for red/black
    l: int  # cards left that win LOWER (or BLACK)
    up: str  # the side h counts: HIGHER or RED
    down: str  # LOWER or BLACK

    @property
    def total(self) -> int:
        return self.h + self.same + self.l

    @property
    def k(self) -> Fraction:
        """Kelly fraction: |h − l| / (h + l); 0 if h == l or nothing can win."""
        if self.h + self.l == 0 or self.h == self.l:
            return Fraction(0)
        return Fraction(abs(self.h - self.l), self.h + self.l)

    @property
    def right(self) -> str | None:
        """The side with more cards (None when there's no edge)."""
        if self.k == 0:
            return None
        return self.up if self.h > self.l else self.down


def odds_hilo(showing: Card, left: list[Card]) -> Odds:
    return Odds(
        sum(1 for c in left if c.rank > showing.rank), sum(1 for c in left if c.rank == showing.rank),
        sum(1 for c in left if c.rank < showing.rank), HIGHER, LOWER,
    )


def odds_redblack(left: list[Card]) -> Odds:
    reds = sum(1 for c in left if c.red)
    return Odds(reds, 0, len(left) - reds, RED, BLACK)


def pct(k: Fraction) -> int:
    """k shown as a whole percent (half up)."""
    return math.floor(k * 100 + Fraction(1, 2))


# ── grading + points ─────────────────────────────────────────────────────────


def grade(odds: Odds, side: str | None, s: Fraction, timeout: bool = False) -> str:
    """Grade one bet. s = your stake as a fraction of capital."""
    k = odds.k
    if timeout:
        return MISS
    if k == 0:
        return DISCIPLINE if s == 0 else MISS
    if s == 0:
        return SAT_OUT
    if side != odds.right:
        return MISS
    off = abs(s - k)
    if off <= max(k / 10, Fraction(3, 100)):
        return PERFECT
    if off <= max(k / 4, Fraction(7, 100)):
        return GOOD
    return OK


def speed_tier(elapsed: Fraction, limit: Fraction) -> str:
    """LIGHTNING within the first 25% of the bet's clock, FAST within 50%, else NORMAL."""
    if elapsed <= limit / 4:
        return LIGHTNING
    if elapsed <= limit / 2:
        return FAST
    return NORMAL


def combo_multiplier(streak: int) -> Fraction:
    return min(1 + COMBO_STEP * streak, COMBO_CAP)


def next_streak(streak: int, g: str) -> int:
    """PERFECT / GOOD / DISCIPLINE extend the streak; OK leaves it; MISS / SAT OUT (and timeouts) reset it."""
    if g in STREAK_GRADES:
        return streak + 1
    return streak if g == OK else 0


def round_half_up(x: Fraction) -> int:
    return math.floor(x + Fraction(1, 2))


def points(g: str, tier: str, streak_before: int) -> int:
    """round(base × speed × combo); speed only counts for PERFECT / GOOD / DISCIPLINE."""
    speed = SPEED[tier] if g in STREAK_GRADES else Fraction(1)
    return round_half_up(BASE[g] * speed * combo_multiplier(streak_before))


# ── money ────────────────────────────────────────────────────────────────────


def stake_amount(capital: int, percent: int) -> int:
    return capital * percent // 100


def snap_stake(percent: int, step: int) -> int:
    """Shift+→ (step +1) / Shift+← (step −1): the next / previous multiple of 25%, clamped to 0–100."""
    if step > 0:
        return min(100, (percent // 25 + 1) * 25)
    return max(0, (percent - 1) // 25 * 25)


def settle(side: str | None, showing: Card | None, nxt: Card) -> int:
    """+1 win, −1 loss, 0 push (same rank) or no side."""
    if side is None:
        return 0
    if side in (RED, BLACK):
        return 1 if nxt.red == (side == RED) else -1
    if nxt.rank == showing.rank:
        return 0
    return 1 if (nxt.rank > showing.rank) == (side == HIGHER) else -1


def capital_bonus(start: int, final: int, bust: bool) -> int:
    """round(1000 × log2(final / start)), only if you didn't bust and finished up."""
    if bust or final <= start:
        return 0
    return math.floor(1000 * math.log2(final / start) + 0.5)


def benchmark(kind: str, cards: list[Card], start: int) -> Fraction:
    """The multiple you'd reach staking exactly k (floored to whole dollars) on the right side every bet."""
    capital = start
    showing = None if kind == REDBLACK else cards[0]
    first = 0 if kind == REDBLACK else 1
    for i in range(first, len(cards)):
        left = cards[i:]
        odds = odds_redblack(left) if kind == REDBLACK else odds_hilo(showing, left)
        amount = math.floor(capital * odds.k)
        capital += amount * settle(odds.right, showing, cards[i]) if odds.right else 0
        showing = cards[i]
        if capital < 1:
            break
    return Fraction(capital, start)
