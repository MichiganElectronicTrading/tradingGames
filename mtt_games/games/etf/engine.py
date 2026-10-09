"""ETF Arb engine: the round state machine on a tick clock. Pure Python, no Textual.

Each round an ETF bid/ask is posted against a basket whose NAV = Σ weight × price. You and three
computer traders (KESTREL, OSPREY, MERLIN) each get at most one trade: BUY at the ask, SELL at the bid,
or SKIP. Everyone draws on the same limited size at each side. Every trade pays a flat fee, and the
first trade of the round earns a bonus on its (gross − fee) when that is positive. P&L settles at the
round's NAV.

Time is a counter of 0.25 s ticks (`now`); the UI feeds real time in with `advance_to()` and tests drive
it directly. One `random.Random(seed)` draws the market; each computer trader has its own RNG seeded
from it, so the same seed gives the same market and the same computer decision times and errors.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from mtt_games.games.etf.config import PRESETS, EtfConfig
from mtt_games.games.etf.model import BUY, SELL, SKIP, RoundPlan, bonus, draw_market, gross, right_call

TICK = 0.25
OPEN, RESULT, RECAP = "open", "result", "recap"
TIMEOUT = "TIMEOUT"
YOU = 0
NAMES = ("YOU", "KESTREL", "OSPREY", "MERLIN")
D = Decimal


def ticks(seconds: float) -> int:
    return round(seconds / TICK)


class EtfSource:
    """What the shared lobby/custom/stats screens need to know about the game."""

    key = "etf"
    title = "ETF ARB"
    item = "stock"
    config_cls = EtfConfig
    presets = PRESETS
    events: dict[str, Any] = {}
    places = 2
    tick = D("0.01")

    def price(self, x: Any) -> str:
        return f"{x:.2f}"

    def settle_range(self, cfg: EtfConfig) -> tuple[int, int]:
        return 50, 600  # NAV stays near a weighted average of the 50–600 starting prices


ETF_SOURCE = EtfSource()


@dataclass(frozen=True)
class Fill:
    who: int
    side: str  # BUY / SELL
    units: int
    price: Decimal
    t: int  # ticks into the round
    gross: Decimal
    fee: Decimal
    bonus: Decimal
    first: bool

    @property
    def net(self) -> Decimal:
        return self.gross - self.fee + self.bonus


@dataclass(frozen=True)
class Decision:
    who: int
    action: str  # BUY / SELL / SKIP / TIMEOUT
    t: int | None  # ticks into the round (None: never decided in time)
    fill: Fill | None = None
    note: str = ""

    @property
    def net(self) -> Decimal:
        return self.fill.net if self.fill else D(0)


@dataclass
class Round:
    plan: RoundPlan
    start: int  # tick the round opened
    size: int  # units at each side when the round opened
    bid_left: int
    ask_left: int
    fills: list[Fill] = field(default_factory=list)
    decisions: dict[int, Decision] = field(default_factory=dict)
    end: int | None = None

    @classmethod
    def open(cls, plan: RoundPlan, start: int, size: int) -> Round:
        return cls(plan, start, size, size, size)

    @property
    def number(self) -> int:
        return self.plan.number

    @property
    def nav(self) -> Decimal:
        return self.plan.nav

    @property
    def first(self) -> Fill | None:
        return self.fills[0] if self.fills else None

    def left(self, side: str) -> int:
        return self.ask_left if side == BUY else self.bid_left


TraderFactory = Callable[["EtfGame", int, random.Random], Any]


class EtfGame:
    SOURCE = ETF_SOURCE
    TICK = TICK

    def __init__(self, config: EtfConfig, mode: str = "CUSTOM", traders: TraderFactory | None = None) -> None:
        if not isinstance(config, EtfConfig):
            raise TypeError("EtfGame needs an EtfConfig")
        config.validate()
        self.config = config
        self.mode = mode
        self.seed = config.seed if config.seed is not None else random.SystemRandom().randrange(1, 1_000_000)
        rng = random.Random(self.seed)
        self.market = draw_market(config, rng)
        seeds = [rng.getrandbits(64) for _ in NAMES[1:]]
        if traders is None:
            from mtt_games.games.etf.traders import make_trader as traders
        self.traders = {seat: traders(self, seat, random.Random(s)) for seat, s in zip(range(1, len(NAMES)), seeds)}
        self.names = NAMES
        self.rounds: list[Round] = []
        self.now = 0
        self.phase = OPEN
        self._start_round()

    @property
    def source(self) -> EtfSource:
        return ETF_SOURCE

    @property
    def round(self) -> Round:
        return self.rounds[-1]

    @property
    def t(self) -> int:
        """Ticks into the current round."""
        return self.now - self.round.start

    @property
    def timer_ticks(self) -> int:
        return ticks(self.config.timer_s)

    def seconds_left(self) -> float:
        return max(0, self.timer_ticks - self.t) * TICK if self.phase == OPEN else 0.0

    def right_units(self, rnd: Round | None = None) -> int:
        """u = min(max units, size at a side at round start)."""
        return min(self.config.max_units, (rnd or self.round).size)

    def right_call(self, rnd: Round | None = None) -> tuple[str, Decimal]:
        r = rnd or self.round
        return right_call(r.nav, r.plan.bid, r.plan.ask, self.right_units(r), self.config.fee)

    def total(self, who: int) -> Decimal:
        return sum((r.decisions[who].net for r in self.rounds if who in r.decisions), D(0))

    # ── clock ───────────────────────────────────────────────────────────────

    def advance(self, n: int = 1) -> None:
        for _ in range(n):
            self.now += 1
            if self.phase == OPEN:
                self._tick()

    def advance_to(self, tick: int) -> None:
        if tick > self.now:
            self.advance(tick - self.now)

    def _start_round(self) -> None:
        plan = self.market.rounds[len(self.rounds)]
        self.rounds.append(Round.open(plan, self.now, self.config.size))
        self.phase = OPEN

    def _tick(self) -> None:
        """Computers whose decision time has come act (in seat order); the round ends at the timer, or
        as soon as everyone has decided."""
        t = self.t
        if t < self.timer_ticks:
            for seat, trader in self.traders.items():
                if self.phase != OPEN:
                    return
                if seat not in self.round.decisions and trader.decide_at(self.round.number) <= t:
                    reason = trader.act()
                    if seat not in self.round.decisions:
                        self._decide(Decision(seat, SKIP, t, note=reason or ""))
        if self.phase == OPEN and (t >= self.timer_ticks or self._everyone_done()):
            self._end_round()

    def _everyone_done(self) -> bool:
        r = self.round
        return YOU in r.decisions and all(
            s in r.decisions or self.traders[s].decide_at(r.number) >= self.timer_ticks for s in self.traders)

    def _end_round(self) -> None:
        r = self.round
        self.phase = RESULT  # first, so recording the leftovers below can't end the round again
        if YOU not in r.decisions:
            self._decide(Decision(YOU, TIMEOUT, None, note="timer ran out"))
        for seat in self.traders:
            if seat not in r.decisions:
                self._decide(Decision(seat, SKIP, None, note="too slow — still pricing at the bell"))
        r.end = self.now

    # ── trading ─────────────────────────────────────────────────────────────

    def can_trade(self, who: int, side: str) -> bool:
        return self.phase == OPEN and who not in self.round.decisions and self.round.left(side) > 0

    def trade(self, who: int, side: str, units: int) -> Fill:
        """`who` buys at the ask (BUY) or sells at the bid (SELL) `units`, from the shared size."""
        r = self.round
        if self.phase != OPEN:
            raise RuntimeError("the round is closed")
        if who in r.decisions:
            raise RuntimeError(f"{self.names[who]} already acted this round")
        if side not in (BUY, SELL):
            raise ValueError(f"not a side: {side!r}")
        if r.left(side) == 0:
            raise ValueError(f"nothing left at the {'ask' if side == BUY else 'bid'}")
        if not 1 <= units <= min(self.config.max_units, r.left(side)):
            raise ValueError(f"units must be 1–{min(self.config.max_units, r.left(side))}")
        plan = r.plan
        price = plan.ask if side == BUY else plan.bid
        g = gross(side, units, plan.nav, plan.bid, plan.ask)
        first = not r.fills
        fill = Fill(who, side, units, price, self.t, g, self.config.fee, bonus(first, g, self.config.fee,
                                                                               self.config.bonus), first)
        if side == BUY:
            r.ask_left -= units
        else:
            r.bid_left -= units
        r.fills.append(fill)
        self._decide(Decision(who, side, self.t, fill))
        return fill

    def _decide(self, decision: Decision) -> None:
        self.round.decisions[decision.who] = decision
        if self.phase == OPEN and self._everyone_done():
            self._end_round()

    # ── your actions ────────────────────────────────────────────────────────

    def buy(self, units: int) -> Fill:
        return self.trade(YOU, BUY, units)

    def sell(self, units: int) -> Fill:
        return self.trade(YOU, SELL, units)

    def skip(self) -> None:
        if self.phase != OPEN or YOU in self.round.decisions:
            raise RuntimeError("no open round to skip")
        self._decide(Decision(YOU, SKIP, self.t))

    def next_round(self) -> None:
        if self.phase != RESULT:
            raise RuntimeError("the round isn't over")
        if len(self.rounds) < self.config.rounds:
            self._start_round()
        else:
            self.phase = RECAP
