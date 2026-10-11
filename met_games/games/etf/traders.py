"""ETF Arb computer traders (KESTREL, OSPREY, MERLIN).

Each trader prices the basket with a noisy NAV = true NAV + a normal error (sd per preset). On an
event round it applies the event correctly with probability `trap_skill`; otherwise it falls for the
trap and uses the table's (unadjusted) weights. It decides once per round, at a decision time drawn
from the preset's window: it trades the side its perceived gap points to, for min(max units, units
left), only if gap × units > fee + $2. A decision time at or past the timer means it skips.

Everything random (decision time, error, event skill) is drawn per round at setup from the trader's
own RNG, so it doesn't depend on what you do.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from met_games.games.etf.model import BUY, SELL

if TYPE_CHECKING:
    from met_games.games.etf.engine import EtfGame

D = Decimal
MARGIN = D(2)  # a trader needs gap × units > fee + $2


def trader_decision(est: Decimal, bid: Decimal, ask: Decimal, bid_left: int, ask_left: int, max_units: int,
                    fee: Decimal) -> tuple[str | None, int, str]:
    """(side or None, units, reason). The side is the one the perceived gap points to: BUY if est > ask,
    SELL if est < bid. Trade min(max_units, units left) only if gap × units > fee + MARGIN."""
    if est > ask:
        side, gap, left = BUY, est - ask, ask_left
    elif est < bid:
        side, gap, left = SELL, bid - est, bid_left
    else:
        return None, 0, "inside the spread"
    if left == 0:
        return None, 0, f"wanted to {side.lower()}, side empty"
    units = min(max_units, left)
    if gap * units <= fee + MARGIN:
        return None, 0, f"gap too small ({gap:.2f} × {units})"
    return side, units, ""


@dataclass(frozen=True)
class Plan:
    """One trader's pre-drawn view of one round."""

    decide_tick: int
    error: Decimal
    applies_event: bool


class Trader:
    def __init__(self, game: EtfGame, seat: int, rng: random.Random) -> None:
        self.game = game
        self.seat = seat
        self.rng = rng
        cfg = game.config
        lo, hi = cfg.decide_min, cfg.decide_max
        self.plans = []
        for _ in range(cfg.rounds):  # draw order per round: decision time, error, event skill
            tick = round(rng.uniform(lo, hi) / game.TICK)
            error = D(str(round(rng.gauss(0, float(cfg.trader_sd)), 4)))
            self.plans.append(Plan(tick, error, rng.random() < cfg.trap_skill))

    def plan(self, number: int) -> Plan:
        return self.plans[number - 1]

    def decide_at(self, number: int) -> int:
        return self.plan(number).decide_tick

    def perceived_nav(self, number: int) -> Decimal:
        rnd = self.game.rounds[number - 1].plan
        p = self.plan(number)
        base = rnd.nav if rnd.event is None or p.applies_event else rnd.naive_nav
        return base + p.error

    def act(self) -> str:
        """Decide now. Trades through the game, or returns why it skipped."""
        g = self.game
        r = g.round
        side, units, reason = trader_decision(self.perceived_nav(r.number), r.plan.bid, r.plan.ask, r.bid_left,
                                              r.ask_left, g.config.max_units, g.config.fee)
        if side is None:
            return reason
        g.trade(self.seat, side, units)
        return ""


def make_trader(game: EtfGame, seat: int, rng: random.Random) -> Trader:
    return Trader(game, seat, rng)
