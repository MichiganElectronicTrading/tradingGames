"""Outcry stage 2: the order book."""

from mtt_games.games.outcry.book import BID, OFFER, Book

A, B, C, D = 0, 1, 2, 3


def book(size=1, limit=10, positions=None):
    return Book(size, limit, positions if positions is not None else [0, 0, 0, 0])


def apply(b: Book, result) -> None:
    """What the game does after a fill: move both positions."""
    if result.fill:
        b.positions[result.fill.buyer] += result.fill.size
        b.positions[result.fill.seller] -= result.fill.size


def test_resting_orders_and_best_prices():
    b = book()
    assert b.place(A, BID, 400).rested and b.place(B, BID, 402).rested and b.place(C, OFFER, 410).rested
    assert (b.best_bid().owner, b.best_bid().price) == (B, 402)
    assert (b.best_offer().owner, b.best_offer().price) == (C, 410)


def test_price_then_time_priority():
    b = book()
    b.place(A, OFFER, 410)
    b.place(B, OFFER, 409)
    b.place(C, OFFER, 409)  # same price as B, later
    r = b.place(D, BID, 412)
    assert (r.fill.seller, r.fill.price) == (B, 409)  # best price first, then earliest
    r = b.place(D, BID, 412)
    assert (r.fill.seller, r.fill.price) == (C, 409)
    r = b.place(D, BID, 412)
    assert (r.fill.seller, r.fill.price) == (A, 410)


def test_crossing_order_trades_at_resting_price():
    b = book()
    b.place(A, OFFER, 405)
    r = b.place(B, BID, 420)
    assert r.fill == r.fill.__class__(buyer=B, seller=A, price=405, size=1, aggressor=B)
    assert r.rested is None and not b.bids and not b.offers
    b.place(C, BID, 398)
    r = b.place(D, OFFER, 390)
    assert (r.fill.buyer, r.fill.seller, r.fill.price, r.fill.aggressor) == (C, D, 398, D)


def test_non_crossing_order_rests():
    b = book()
    b.place(A, OFFER, 405)
    r = b.place(B, BID, 404)
    assert r.fill is None and r.rested.price == 404


def test_new_order_replaces_old_and_loses_time_priority():
    b = book()
    b.place(A, BID, 400)
    b.place(B, BID, 401)
    b.place(A, BID, 401)  # replaces A's 400; now behind B at 401
    assert [o.owner for o in b.bids if o.owner == A] == [A] and len(b.bids) == 2
    assert b.order_of(A, BID).price == 401
    r = b.place(C, OFFER, 401)
    assert r.fill.buyer == B


def test_cancel_one_side_or_all():
    b = book()
    b.place(A, BID, 400)
    b.place(A, OFFER, 410)
    b.place(B, BID, 399)
    assert [o.side for o in b.cancel(A, BID)] == [BID] and b.order_of(A, OFFER)
    b.place(A, BID, 400)
    assert len(b.cancel(A)) == 2 and b.order_of(A, BID) is None and b.order_of(A, OFFER) is None
    assert b.order_of(B, BID)


def test_no_self_trades():
    b = book()
    b.place(A, OFFER, 405)
    r = b.place(A, BID, 405)
    assert r.error == "would trade with your own offer at 405" and not b.bids
    r = b.place(A, BID, 404)
    assert r.ok and r.fill is None
    r = b.place(A, OFFER, 404)
    assert "own bid" in r.error
    assert b.take(A, BID).error == "no offer to lift"  # the only offer is A's own
    b.place(B, OFFER, 407)
    r = b.take(A, BID)
    assert (r.fill.seller, r.fill.price) == (B, 407)  # skips A's own 405


def test_take_hits_best_bid():
    b = book()
    b.place(A, BID, 400)
    b.place(B, BID, 402)
    r = b.take(C, OFFER)
    assert (r.fill.buyer, r.fill.seller, r.fill.price) == (B, C, 402)
    assert book().take(C, OFFER).error == "no bid to hit"


def test_limit_rejects_orders_and_takes():
    b = book(limit=10, positions=[10, -10, 0, 0])
    assert "limit" in b.place(A, BID, 400).error
    assert b.place(A, OFFER, 410).ok  # selling reduces A's position
    assert "limit" in b.place(B, OFFER, 410).error
    assert "limit" in b.take(A, BID).error


def test_resting_order_cancelled_when_its_owner_hits_the_limit():
    b = book(limit=10, positions=[9, 0, 0, 0])
    b.place(A, BID, 405)  # fine at +9
    b.place(B, OFFER, 420)
    apply(b, b.take(A, BID))  # A buys → +10; its resting bid can no longer fill
    assert b.positions[A] == 10
    r = b.place(C, OFFER, 400)  # would hit A's bid
    assert r.fill is None and [o.owner for o in r.cancelled] == [A] and r.rested.owner == C


def test_trade_size():
    b = book(size=3)
    b.place(A, OFFER, 405)
    r = b.place(B, BID, 405)
    assert r.fill.size == 3


def test_end_of_round_wipe():
    b = book()
    for seat, side, price in ((A, BID, 1), (B, OFFER, 9), (C, BID, 2)):
        b.place(seat, side, price)
    b.clear()
    assert not b.bids and not b.offers and b.best_bid() is None and b.best_offer() is None
