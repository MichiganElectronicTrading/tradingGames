"""Cards and the 52-card deck."""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass

SUITS = ("♠", "♥", "♦", "♣")
RED_SUITS = frozenset({"♥", "♦"})
RANKS = tuple(range(2, 15))  # J=11, Q=12, K=13, A=14
_FACE = {11: "J", 12: "Q", 13: "K", 14: "A"}


@dataclass(frozen=True)
class Card:
    rank: int
    suit: str

    @property
    def label(self) -> str:
        return _FACE.get(self.rank, str(self.rank))

    @property
    def is_red(self) -> bool:
        return self.suit in RED_SUITS

    def __str__(self) -> str:
        return f"{self.label}{self.suit}"


def build_deck(removed_ranks: Iterable[int] = ()) -> list[Card]:
    """A fresh, ordered deck with any `removed_ranks` taken out."""
    removed = set(removed_ranks)
    return [Card(rank, suit) for suit in SUITS for rank in RANKS if rank not in removed]


def deal(rng: random.Random, n: int, removed_ranks: Iterable[int] = ()) -> list[Card]:
    """Shuffle a fresh deck and deal `n` cards without replacement."""
    deck = build_deck(removed_ranks)
    rng.shuffle(deck)
    return deck[:n]
