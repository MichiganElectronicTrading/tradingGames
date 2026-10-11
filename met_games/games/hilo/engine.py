"""Higher or Lower engine: the bet-by-bet state machine on a tick clock. Pure Python, no Textual.

A card is showing; you call the next one (higher/lower, or red/black) and stake a whole percent of your
capital at even money. Bets are untimed by default; with `timed` on, each bet has its own clock and running
out is a stake-0 MISS. After each lock the
game pauses in REVEAL until `next_bet()` (the UI's reveal flash), so the flash never eats the next bet's
time. Capital below 1 busts the game immediately.

Time is a counter of 0.25 s ticks; the UI feeds real (or injected) time in with `advance_to()`. The deck
order comes only from the seed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from met_games.games.hilo.config import PRESETS, REDBLACK, HiloConfig
from met_games.games.hilo.model import (
    BLACK,
    HIGHER,
    LOWER,
    NORMAL,
    RED,
    Card,
    Odds,
    bets_in,
    build_deck,
    capital_bonus,
    combo_multiplier,
    grade,
    next_streak,
    odds_hilo,
    odds_redblack,
    points,
    settle,
    speed_tier,
    stake_amount,
)

TICK = 0.25
BET, REVEAL, OVER = "bet", "reveal", "over"


def ticks(seconds: float) -> int:
    return round(seconds / TICK)


class HiloSource:
    """What the shared custom/how-to screens need to know about the game."""

    key = "hilo"
    title = "HI/LO"
    item = "card"
    config_cls = HiloConfig
    presets = PRESETS
    events: dict[str, Any] = {}
    places = 0
    tick = 1

    def price(self, x: Any) -> str:
        return f"{x:.0f}"

    def settle_range(self, cfg: HiloConfig) -> tuple[int, int]:
        return 0, cfg.start_capital


HILO_SOURCE = HiloSource()


@dataclass(frozen=True)
class Bet:
    number: int  # 1-based
    showing: Card | None  # None on a red/black bet
    next: Card
    odds: Odds
    side: str | None
    percent: int
    amount: int
    result: int  # +1 win, −1 loss, 0 push / no stake
    capital_before: int
    capital_after: int
    grade: str
    elapsed: int  # ticks into this bet's clock
    tier: str  # LIGHTNING / FAST / NORMAL
    streak_before: int
    points: int
    timeout: bool

    @property
    def combo(self) -> Fraction:
        return combo_multiplier(self.streak_before)

    @property
    def change(self) -> int:
        return self.capital_after - self.capital_before


class HiloGame:
    SOURCE = HILO_SOURCE
    TICK = TICK

    def __init__(self, config: HiloConfig, mode: str = "CUSTOM") -> None:
        if not isinstance(config, HiloConfig):
            raise TypeError("HiloGame needs a HiloConfig")
        config.validate()
        self.config = config
        self.mode = mode
        self.seed = config.seed if config.seed is not None else random.SystemRandom().randrange(1, 1_000_000)
        self.cards = build_deck(config.deck, random.Random(self.seed))
        self.redblack = config.deck == REDBLACK
        self.start = config.start_capital
        self.capital = self.start
        self.bets: list[Bet] = []
        self.streak = 0
        self.best_streak = 0
        self.best_combo = Fraction(1)
        self.pos = 0 if self.redblack else 1  # index of the card being bet on
        self.bust = False
        self.now = 0
        self.bet_start = 0
        self.phase = BET

    @property
    def source(self) -> HiloSource:
        return HILO_SOURCE

    @property
    def total_bets(self) -> int:
        return bets_in(self.config.deck, len(self.cards))

    @property
    def number(self) -> int:
        """The current (or just-locked) bet's number, 1-based."""
        return len(self.bets) + (1 if self.phase == BET else 0)

    @property
    def sides(self) -> tuple[str, str]:
        return (RED, BLACK) if self.redblack else (HIGHER, LOWER)

    @property
    def showing(self) -> Card | None:
        """The card the next bet is measured against (None on red/black, where nothing is compared)."""
        return None if self.redblack else self.cards[self.pos - 1]

    @property
    def left(self) -> list[Card]:
        return self.cards[self.pos:]

    def odds(self) -> Odds:
        return odds_redblack(self.left) if self.redblack else odds_hilo(self.showing, self.left)

    @property
    def limit_ticks(self) -> int:
        return ticks(self.config.time_s)

    def elapsed(self) -> int:
        return self.now - self.bet_start

    def seconds_left(self) -> float:
        return max(0, self.limit_ticks - self.elapsed()) * TICK if self.phase == BET else 0.0

    # ── clock ───────────────────────────────────────────────────────────────

    def advance(self, n: int = 1) -> None:
        for _ in range(n):
            self.now += 1
            if self.config.timed and self.phase == BET and self.elapsed() >= self.limit_ticks:
                self._resolve(None, 0, timeout=True)

    def advance_to(self, tick: int) -> None:
        if tick > self.now:
            self.advance(tick - self.now)

    # ── betting ─────────────────────────────────────────────────────────────

    def lock(self, side: str | None, percent: int) -> Bet:
        """Lock this bet: `side` and a whole `percent` (0–100) of capital. Stake 0 is a sit-out."""
        if self.phase != BET:
            raise RuntimeError("no bet is open")
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ValueError("stake must be a whole percent 0–100")
        if side is not None and side not in self.sides:
            raise ValueError(f"side must be one of {self.sides}")
        if percent > 0 and side is None:
            raise ValueError("pick a side to stake on")
        return self._resolve(side, percent, timeout=False)

    def _resolve(self, side: str | None, percent: int, timeout: bool) -> Bet:
        odds = self.odds()
        nxt = self.cards[self.pos]
        amount = stake_amount(self.capital, percent)
        result = settle(side, self.showing, nxt) if percent else 0
        before = self.capital
        self.capital += amount * result
        if self.config.timed:
            elapsed = min(self.elapsed(), self.limit_ticks)
            tier = speed_tier(Fraction(elapsed, 4), Fraction(self.config.time_s))  # 4 ticks a second
        else:
            elapsed, tier = self.elapsed(), NORMAL  # untimed: no speed multiplier
        g = grade(odds, side, Fraction(percent, 100), timeout)
        pts = points(g, tier, self.streak)
        bet = Bet(len(self.bets) + 1, self.showing, nxt, odds, side, percent, amount, result, before, self.capital, g,
                  elapsed, tier, self.streak, pts, timeout)
        self.bets.append(bet)
        self.best_combo = max(self.best_combo, bet.combo)
        self.streak = next_streak(self.streak, g)
        self.best_streak = max(self.best_streak, self.streak)
        self.pos += 1
        self.bust = self.capital < 1
        self.phase = REVEAL
        return bet

    def next_bet(self) -> None:
        """After the reveal: open the next bet, or end the game (bust, or the deck is done)."""
        if self.phase != REVEAL:
            raise RuntimeError("nothing to move on from")
        if self.bust or len(self.bets) >= self.total_bets:
            self.phase = OVER
            return
        self.phase = BET
        self.bet_start = self.now

    # ── score ───────────────────────────────────────────────────────────────

    @property
    def bet_points(self) -> int:
        return sum(b.points for b in self.bets)

    @property
    def bonus(self) -> int:
        return capital_bonus(self.start, self.capital, self.bust)

    @property
    def score(self) -> int:
        return self.bet_points + self.bonus

    @property
    def multiple(self) -> Fraction:
        return Fraction(self.capital, self.start)
