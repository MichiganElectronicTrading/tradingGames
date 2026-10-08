"""The live order book for the open outcry. Pure Python.

Every order is for the game's trade size. Each player has at most one bid and one offer; a new one
replaces the old. Matching is price then time priority, and a crossing order trades at the resting
order's price. No self-trades: an order that would cross its owner's own resting order is rejected.
An order that could breach its owner's position limit is rejected; a resting order whose owner can no
longer take the fill is cancelled when it would match.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

BID, OFFER = "bid", "offer"


@dataclass(frozen=True)
class Order:
    owner: int  # seat
    side: str  # BID / OFFER
    price: int
    size: int
    seq: int  # arrival order, for time priority


@dataclass(frozen=True)
class Fill:
    buyer: int
    seller: int
    price: int
    size: int
    aggressor: int  # the seat whose order or take crossed the book


@dataclass
class Result:
    fill: Fill | None = None
    rested: Order | None = None
    error: str | None = None
    cancelled: list[Order] = field(default_factory=list)  # resting orders pulled because of their owner's limit

    @property
    def ok(self) -> bool:
        return self.error is None


class Book:
    def __init__(self, size: int, limit: int, positions: Sequence[int]) -> None:
        self.size = size
        self.limit = limit
        self.positions = positions  # live view of every seat's position (the game updates it after fills)
        self.bids: list[Order] = []
        self.offers: list[Order] = []
        self._seq = 0

    # ── queries ─────────────────────────────────────────────────────────────

    def sorted_bids(self) -> list[Order]:
        return sorted(self.bids, key=lambda o: (-o.price, o.seq))

    def sorted_offers(self) -> list[Order]:
        return sorted(self.offers, key=lambda o: (o.price, o.seq))

    def best_bid(self, exclude: int | None = None) -> Order | None:
        return next((o for o in self.sorted_bids() if o.owner != exclude), None)

    def best_offer(self, exclude: int | None = None) -> Order | None:
        return next((o for o in self.sorted_offers() if o.owner != exclude), None)

    def order_of(self, owner: int, side: str) -> Order | None:
        return next((o for o in (self.bids if side == BID else self.offers) if o.owner == owner), None)

    def can_trade(self, seat: int, side: str) -> bool:
        """Would one more fill on `side` (BID = buying) keep `seat` within the limit?"""
        delta = self.size if side == BID else -self.size
        return abs(self.positions[seat] + delta) <= self.limit

    # ── actions ─────────────────────────────────────────────────────────────

    def place(self, owner: int, side: str, price: int) -> Result:
        """Post a limit order (replacing the owner's order on that side). Trades at most once."""
        if not self.can_trade(owner, side):
            return Result(error=f"{'bid' if side == BID else 'offer'} would breach your ±{self.limit} limit")
        mine = self.order_of(owner, OFFER if side == BID else BID)
        if mine is not None and (price >= mine.price if side == BID else price <= mine.price):
            other = "offer" if side == BID else "bid"
            return Result(error=f"would trade with your own {other} at {mine.price}")
        self.cancel(owner, side)
        result = Result()
        resting = self.sorted_offers() if side == BID else self.sorted_bids()
        for o in resting:
            if (o.price > price) if side == BID else (o.price < price):
                break
            if not self.can_trade(o.owner, OFFER if side == BID else BID):
                self._remove(o)
                result.cancelled.append(o)
                continue
            self._remove(o)
            buyer, seller = (owner, o.owner) if side == BID else (o.owner, owner)
            result.fill = Fill(buyer, seller, o.price, self.size, owner)
            return result
        self._seq += 1
        order = Order(owner, side, price, self.size, self._seq)
        (self.bids if side == BID else self.offers).append(order)
        result.rested = order
        return result

    def take(self, owner: int, side: str) -> Result:
        """Lift the best offer (side BID) or hit the best bid (side OFFER) from someone else."""
        if not self.can_trade(owner, side):
            return Result(error=f"would breach your ±{self.limit} limit")
        result = Result()
        resting = self.sorted_offers() if side == BID else self.sorted_bids()
        for o in resting:
            if o.owner == owner:
                continue
            if not self.can_trade(o.owner, OFFER if side == BID else BID):
                self._remove(o)
                result.cancelled.append(o)
                continue
            self._remove(o)
            buyer, seller = (owner, o.owner) if side == BID else (o.owner, owner)
            result.fill = Fill(buyer, seller, o.price, self.size, owner)
            return result
        result.error = f"no {'offer to lift' if side == BID else 'bid to hit'}"
        return result

    def cancel(self, owner: int, side: str | None = None) -> list[Order]:
        gone = [o for o in self.bids + self.offers if o.owner == owner and side in (None, o.side)]
        for o in gone:
            self._remove(o)
        return gone

    def clear(self) -> None:
        self.bids.clear()
        self.offers.clear()

    def _remove(self, order: Order) -> None:
        (self.bids if order.side == BID else self.offers).remove(order)
