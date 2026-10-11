"""Computer traders. Each one prices the contract from its OWN knowledge (exact fair), makes no use of
anyone else's private information, and draws every random choice from its own seeded RNG.

Shared rules (every style):
- As forced opener: mid = estimate, width = uniform integer in the style's OPEN_WIDTHS range.
- As forced responder: buy if estimate ≥ ask + 1, sell if estimate ≤ bid − 1, else pass.
- On the outcry: after a random cooldown it takes one action, then draws the next cooldown.
- Hard ("learns from the tape"): every trade moves the estimate 25% of the way toward its price.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from met_games.games.outcry.book import BID, OFFER
from met_games.games.outcry.config import ANCHOR, CHASER, MAKER, PASSIVE, SNIPER

if TYPE_CHECKING:
    from met_games.games.outcry.engine import OutcryGame, Trade

BUY, SELL, PASS = "buy", "sell", "pass"
LEARN_RATE = 0.25
RESPOND_EDGE = 1  # forced responder: buy if est ≥ ask + 1, sell if est ≤ bid − 1
OPEN_WIDTHS: dict[str, tuple[int, int]] = {  # forced-open width range by style
    MAKER: (4, 8), SNIPER: (6, 10), CHASER: (6, 10), ANCHOR: (8, 14), PASSIVE: (12, 20),
}


def respond_rule(est: float, bid: int, ask: int) -> str:
    if est >= ask + RESPOND_EDGE:
        return BUY
    if est <= bid - RESPOND_EDGE:
        return SELL
    return PASS


def quote_around(est: float, width: int) -> tuple[int, int]:
    bid = round(est - width / 2)
    return bid, bid + width


class Trader:
    style = "BASE"
    slow = 1.0  # cooldown multiplier
    open_width = OPEN_WIDTHS[MAKER]  # each style sets its own; the bare base trader opens like a MAKER

    def __init__(self, game: OutcryGame, seat: int, rng: random.Random) -> None:
        self.game = game
        self.seat = seat
        self.rng = rng
        self.offset = 0.0  # learned from the tape (Hard only)

    # ── estimate ────────────────────────────────────────────────────────────

    def base_estimate(self) -> float:
        """Exact fair from this trader's own knowledge."""
        return self.game.fair(self.seat)

    def estimate(self) -> float:
        return self.base_estimate() + self.offset

    def on_trade(self, trade: Trade) -> None:
        if self.game.config.learns:
            self.offset += LEARN_RATE * (trade.price - self.estimate())

    # ── forced open / response ──────────────────────────────────────────────

    def open_quote(self) -> tuple[int, int]:
        return self.game.fit_quote(*quote_around(self.estimate(), self.rng.randint(*self.open_width)))

    def respond(self, bid: int, ask: int) -> str:
        return respond_rule(self.estimate(), bid, ask)

    # ── outcry ──────────────────────────────────────────────────────────────

    def cooldown_ticks(self) -> int:
        lo, hi = self.game.config.cooldown
        seconds = self.rng.uniform(lo, hi) * self.slow
        return max(1, round(seconds / self.game.TICK))

    def act(self) -> None:
        """One outcry action. The base trader stays out of the book."""


# ── styles ───────────────────────────────────────────────────────────────────

MAKER_WIDTH = (3, 6)
PASSIVE_WIDTH = (8, 14)
SNIPER_EDGE = 2  # take only when the price is at least this much better than the estimate
PASSIVE_EDGE = 5  # "rarely takes"
CHASER_EDGE = ANCHOR_EDGE = 1
PASSIVE_SLOW = 2.0  # cooldown multiplier
CHASE = 0.5  # CHASER moves its estimate half-way to the last trade price


def take_decision(est: float, best_bid: int | None, best_offer: int | None, edge: float) -> str | None:
    """BID to lift the offer, OFFER to hit the bid, or None. A side qualifies when its price is at least
    `edge` better than `est`; if both do, the bigger edge wins (ties: lift)."""
    buy = est - best_offer if best_offer is not None else None
    sell = best_bid - est if best_bid is not None else None
    if buy is not None and buy >= edge and (sell is None or buy >= sell):
        return BID
    if sell is not None and sell >= edge:
        return OFFER
    return None


def needs_requote(has_bid: bool, has_offer: bool, traded: bool, quoted_mid: int | None, est: float) -> bool:
    """A quoting trader requotes when a side is missing, after it traded, or when its estimate moved."""
    return not (has_bid and has_offer) or traded or quoted_mid is None or round(est) != quoted_mid


def anchor_estimate(known: list[int], players: int) -> float:
    """The naive estimate: players × the mean of the numbers it knows. Ignores range logic entirely."""
    return players * sum(known) / len(known)


def chase(est: float, last_price: int | None) -> float:
    return est if last_price is None else est + CHASE * (last_price - est)


class Quoter(Trader):
    """Keeps a two-sided quote around its estimate; may also take when the edge is big enough."""

    width = MAKER_WIDTH
    take_edge: float | None = None

    def __init__(self, game: OutcryGame, seat: int, rng: random.Random) -> None:
        super().__init__(game, seat, rng)
        self.quoted_mid: int | None = None
        self.traded = False

    def on_trade(self, trade: Trade) -> None:
        super().on_trade(trade)
        if self.seat in (trade.buyer, trade.seller):
            self.traded = True

    def act(self) -> None:
        est = self.estimate()
        if self.take_edge is not None and self.try_take(est, self.take_edge):
            return
        book = self.game.book
        has_bid = book.order_of(self.seat, BID) is not None
        has_offer = book.order_of(self.seat, OFFER) is not None
        if needs_requote(has_bid, has_offer, self.traded, self.quoted_mid, est):
            self.requote(est)

    def requote(self, est: float) -> None:
        game = self.game
        bid, ask = quote_around(est, self.rng.randint(*self.width))
        game.cancel(self.seat)
        self.quoted_mid, self.traded = round(est), False
        if game.book.can_trade(self.seat, BID) and bid >= 0:
            game.place(self.seat, BID, bid)
        if game.book.can_trade(self.seat, OFFER):
            game.place(self.seat, OFFER, ask)

    def try_take(self, est: float, edge: float) -> bool:
        book = self.game.book
        best_bid, best_offer = book.best_bid(exclude=self.seat), book.best_offer(exclude=self.seat)
        side = take_decision(est, best_bid.price if best_bid else None, best_offer.price if best_offer else None, edge)
        if side is None or not book.can_trade(self.seat, side):
            return False
        return self.game.take(self.seat, side).fill is not None


class MakerTrader(Quoter):
    style = MAKER
    open_width = OPEN_WIDTHS[MAKER]


class PassiveTrader(Quoter):
    style = PASSIVE
    open_width = OPEN_WIDTHS[PASSIVE]
    width = PASSIVE_WIDTH
    take_edge = PASSIVE_EDGE
    slow = PASSIVE_SLOW


class ChaserTrader(Quoter):
    style = CHASER
    open_width = OPEN_WIDTHS[CHASER]
    take_edge = CHASER_EDGE

    def estimate(self) -> float:
        return chase(super().estimate(), self.game.last_price)


class AnchorTrader(Quoter):
    style = ANCHOR
    open_width = OPEN_WIDTHS[ANCHOR]
    take_edge = ANCHOR_EDGE

    def base_estimate(self) -> float:
        return anchor_estimate(self.game.knowledge(self.seat).known, self.game.config.players)


class SniperTrader(Trader):
    style = SNIPER
    open_width = OPEN_WIDTHS[SNIPER]

    def act(self) -> None:
        book = self.game.book
        est = self.estimate()
        best_bid, best_offer = book.best_bid(exclude=self.seat), book.best_offer(exclude=self.seat)
        side = take_decision(est, best_bid.price if best_bid else None, best_offer.price if best_offer else None,
                             SNIPER_EDGE)
        if side is not None and book.can_trade(self.seat, side):
            self.game.take(self.seat, side)


STYLE_CLASSES: dict[str, type[Trader]] = {
    MAKER: MakerTrader, SNIPER: SniperTrader, PASSIVE: PassiveTrader, CHASER: ChaserTrader, ANCHOR: AnchorTrader,
}


def make_trader(game: OutcryGame, seat: int, style: str, rng: random.Random) -> Trader:
    return STYLE_CLASSES[style](game, seat, rng)
