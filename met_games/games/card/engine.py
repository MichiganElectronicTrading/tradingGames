"""Card Game engine: the card source (deal, values, fair value, range) on top of the shared core.

Hidden cards are a uniform draw without replacement from every card the player can't see.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any

from met_games.games.card.config import PRESETS, CardConfig
from met_games.games.card.deck import Card, build_deck, deal
from met_games.games.card.events import EVENTS, card_value, removed_ranks
from met_games.games.sumgame.engine import (  # noqa: F401  (re-exported Card Game API)
    BROKE,
    BUY,
    MISSED_EDGE,
    OUT_OF_RISK,
    PASS,
    SELL,
    SIZE_CAP,
    TIMEOUT,
    Decision,
    SumSession,
    edge_per_unit,
    make_quote,
    risk_limits,
    trade_pnl,
)
from met_games.games.sumgame.engine import Round as SumRound
from met_games.games.sumgame.source import DOUBLE_HIDDEN, Market, Source


def fair_and_range(
    up_values: Sequence[int], rest_values: Sequence[int], k: int, double_hidden: bool = False
) -> tuple[float, int, int]:
    """Exact expected settlement and its (min, max) given face-up values and the `rest` pool.

    The k hidden cards are a uniform draw without replacement from `rest`, so each hidden card's
    expected value is mean(rest). With double_hidden one hidden card counts twice.
    """
    s = sum(up_values)
    if k == 0:
        return float(s), s, s
    mean = math.fsum(rest_values) / len(rest_values)
    ordered = sorted(rest_values)
    lo, hi = ordered[:k], ordered[-k:]
    fair = s + k * mean
    settle_min, settle_max = s + sum(lo), s + sum(hi)
    if double_hidden:
        fair += mean
        settle_min += lo[0]
        settle_max += hi[-1]
    return fair, settle_min, settle_max


def market_state(up_cards: Sequence[Card], event: str | None, hidden: int) -> Market:
    up_set = set(up_cards)
    rest = [card_value(c, event) for c in build_deck(removed_ranks(event)) if c not in up_set]
    up = [card_value(c, event) for c in up_cards]
    double = event == DOUBLE_HIDDEN and hidden > 0
    fair, lo, hi = fair_and_range(up, rest, hidden, double)
    return Market(sum(up), hidden, math.fsum(rest) / len(rest), len(rest), double, fair, lo, hi)


def config_settle_range(cfg: CardConfig) -> tuple[int, int]:
    """Lowest and highest settlement any round under `cfg` could produce (all cards hidden)."""
    events: list[str | None] = [] if cfg.event_freq >= 1 and cfg.enabled_events else [None]
    if cfg.event_freq > 0:
        events += [e for e in cfg.enabled_events if e in EVENTS]
    lo, hi = math.inf, -math.inf
    sizes = range(max(2, min(cfg.n_cards_min, cfg.n_cards_max)), min(10, max(cfg.n_cards_min, cfg.n_cards_max)) + 1)
    for event in events:
        values = [card_value(c, event) for c in build_deck(removed_ranks(event))]
        for n in sizes:
            double = event == DOUBLE_HIDDEN and cfg.face_up_min < n
            _, a, b = fair_and_range([], values, n, double)
            lo, hi = min(lo, a), max(hi, b)
    return int(lo), int(hi)


class CardSource(Source):
    key = "card"
    title = "CARD GAME"
    item = "card"
    mean_label = "deck mean"
    config_cls = CardConfig
    presets = PRESETS
    events = EVENTS

    def deal(self, rng: random.Random, n: int, event: str | None) -> list[Card]:
        return deal(rng, n, removed_ranks(event))

    def value(self, item: Card, event: str | None) -> int:
        return card_value(item, event)

    def market(self, up_items: Sequence[Card], event: str | None, hidden: int) -> Market:
        return market_state(up_items, event, hidden)

    def settle_range(self, cfg: CardConfig) -> tuple[int, int]:
        return config_settle_range(cfg)

    def explain_notes(self, m: Market) -> list[str]:
        notes = [
            f"face up {m.up_sum}: sum of the cards you could see",
            f"deck mean {m.deck_mean:.2f}: average of the {m.deck_size} cards not face up — each hidden card "
            "is a uniform draw from them",
        ]
        if m.double_hidden:
            notes.append("one hidden card counts twice, so there are k+1 hidden draws")
        return notes

    def event_note(self, event: str) -> str:
        e = EVENTS[event]
        note = f"event {e.name}: {e.rule}"
        if event == "no_twos":
            return note + " — the deck had 48 cards"
        if event != DOUBLE_HIDDEN:
            return note + " — applied to face-up values and the deck mean"
        return note


CARD = CardSource()


class Round(SumRound):
    SOURCE = CARD

    @property
    def cards(self) -> list[Any]:
        return self.items


class CardSession(SumSession):
    ROUND = Round
