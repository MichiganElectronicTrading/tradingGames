"""Market events: rule changes announced before the quote."""

from __future__ import annotations

from dataclasses import dataclass

from met_games.games.card.deck import Card


@dataclass(frozen=True)
class MarketEvent:
    key: str
    name: str
    rule: str
    removed_ranks: frozenset[int] = frozenset()


EVENTS: dict[str, MarketEvent] = {
    e.key: e
    for e in (
        MarketEvent("face_ten", "FACE CARDS TEN", "J, Q, K count as 10"),
        MarketEvent("no_twos", "NO TWOS", "all 2s removed from the deck before the deal", frozenset({2})),
        MarketEvent("aces_one", "ACES LOW", "aces count as 1"),
        MarketEvent("double_hidden", "DOUBLE DOWN", "one hidden card counts double (it stays hidden)"),
        MarketEvent("red_negative", "RED INK", "hearts and diamonds count negative (face-up ones too)"),
    )
}
EVENT_KEYS: tuple[str, ...] = tuple(EVENTS)


def card_value(card: Card, event: str | None) -> int:
    """A card's settlement value under the active event (double_hidden is applied at settlement)."""
    if event == "face_ten" and card.rank in (11, 12, 13):
        return 10
    if event == "aces_one" and card.rank == 14:
        return 1
    if event == "red_negative" and card.is_red:
        return -card.rank
    return card.rank


def removed_ranks(event: str | None) -> frozenset[int]:
    return EVENTS[event].removed_ranks if event else frozenset()
