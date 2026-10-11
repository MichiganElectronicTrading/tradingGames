"""The source interface: what a sum game plugs into the shared core.

A source deals the items (cards, dice, ...), values them under the active event, and computes
fair value and the settle range from what is face up. Everything else (quotes, risk, P&L,
scoring, screens) is shared. Pure Python, no UI imports.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, ClassVar, Protocol

from met_games.games.sumgame.config import SumConfig

DOUBLE_HIDDEN = "double_hidden"  # every game's "one hidden item counts twice" event


@dataclass(frozen=True)
class Market:
    """What the player could know at one moment: the inputs to fair value and its result."""

    up_sum: int
    hidden: int
    deck_mean: float  # expected value of one hidden item
    deck_size: int  # how many equally likely values that mean is over
    double_hidden: bool
    fair: float
    settle_min: int
    settle_max: int


class EventInfo(Protocol):
    key: str
    name: str
    rule: str


class Source(ABC):
    key: ClassVar[str]  # registry / file key: "card"
    title: ClassVar[str]  # "CARD GAME"
    item: ClassVar[str]  # singular item name: "card"
    mean_label: ClassVar[str]  # what the per-item mean is called in explanations: "deck mean"
    config_cls: ClassVar[type[SumConfig]]
    presets: ClassVar[Mapping[str, SumConfig]]
    events: ClassVar[Mapping[str, EventInfo]]

    @abstractmethod
    def deal(self, rng: random.Random, n: int, event: str | None) -> list[Any]:
        """Deal n items for a round, using only `rng`."""

    @abstractmethod
    def value(self, item: Any, event: str | None) -> int:
        """An item's settlement value under the event (double_hidden is applied at settlement)."""

    @abstractmethod
    def market(self, up_items: Sequence[Any], event: str | None, hidden: int) -> Market:
        """Fair value and settle range given the face-up items and the number still hidden."""

    @abstractmethod
    def settle_range(self, cfg: SumConfig) -> tuple[int, int]:
        """Lowest and highest settlement any round under `cfg` could produce."""

    @abstractmethod
    def explain_notes(self, m: Market) -> list[str]:
        """Lines explaining where `m`'s inputs come from (shown under the fair-value formula)."""

    @abstractmethod
    def event_note(self, event: str) -> str:
        """How the active event entered the fair-value calculation."""

    def label(self, item: Any) -> str:
        """Short text for an item (CSV, settle line)."""
        return str(item)

    def flip_label(self, item: Any) -> str:
        """How the round log names an item that just turned face up."""
        return self.label(item)

    @property
    def noun(self) -> str:
        return self.config_cls.NOUN

    @property
    def tick(self) -> int | Decimal:
        return self.config_cls.TICK

    @property
    def places(self) -> int:
        return self.config_cls.PRICE_PLACES

    def price(self, x: Any) -> str:
        return self.config_cls.price(x)

    def to_money(self, x: Any) -> int | Decimal:
        """Money in this game's exact type: int for whole-dollar ticks, Decimal otherwise."""
        return Decimal(str(x)) if isinstance(self.tick, Decimal) else x
