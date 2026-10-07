"""Card Game configuration: CardConfig and the EASY/MEDIUM/HARD presets."""

from __future__ import annotations

from dataclasses import dataclass

from mtt_games.games.card.events import EVENT_KEYS
from mtt_games.games.sumgame.config import SumConfig


@dataclass(frozen=True)
class CardConfig(SumConfig):
    NOUN = "cards"
    COUNT_FIELDS = ("n_cards_min", "n_cards_max")
    TICK = 1
    PRICE_PLACES = 0
    SPREAD_MAX = 8
    EVENT_KEYS = EVENT_KEYS

    n_cards_min: int = 3
    n_cards_max: int = 3


EASY = CardConfig()
MEDIUM = CardConfig(
    n_cards_min=5, n_cards_max=5, face_up_min=0, face_up_max=2, rounds=4, timer_s=30,
    spread=3, quote_noise_sd=2.0, sizing="choose",
)
HARD = CardConfig(
    n_cards_min=6, n_cards_max=8, face_up_min=1, face_up_max=3, rounds=6, timer_s=15,
    spread=2, quote_noise_sd=1.5, sizing="choose", mid_round_flip=True, stale_quotes=True,
    event_freq=1.0, enabled_events=EVENT_KEYS,
)

PRESETS: dict[str, CardConfig] = {"EASY": EASY, "MEDIUM": MEDIUM, "HARD": HARD}
