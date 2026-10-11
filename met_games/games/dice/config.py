"""Dice Game configuration: DiceConfig (prices in 0.25 ticks) and the EASY/MEDIUM/HARD presets."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from met_games.games.dice.events import EVENT_KEYS
from met_games.games.sumgame.config import SumConfig


@dataclass(frozen=True)
class DiceConfig(SumConfig):
    NOUN = "dice"
    COUNT_FIELDS = ("n_dice_min", "n_dice_max")
    TICK = Decimal("0.25")
    PRICE_PLACES = 2
    SPREAD_MAX = Decimal("8.00")
    EVENT_KEYS = EVENT_KEYS

    spread: Decimal = Decimal("2.00")
    quote_noise_sd: float = 1.5
    n_dice_min: int = 3
    n_dice_max: int = 3


EASY = DiceConfig()
MEDIUM = DiceConfig(
    n_dice_min=5, n_dice_max=5, face_up_min=0, face_up_max=2, rounds=4, timer_s=30,
    spread=Decimal("1.50"), quote_noise_sd=1.0, sizing="choose",
)
HARD = DiceConfig(
    n_dice_min=6, n_dice_max=8, face_up_min=1, face_up_max=3, rounds=6, timer_s=15,
    spread=Decimal("1.00"), quote_noise_sd=0.75, sizing="choose", mid_round_flip=True, stale_quotes=True,
    event_freq=1.0, enabled_events=EVENT_KEYS,
)

PRESETS: dict[str, DiceConfig] = {"EASY": EASY, "MEDIUM": MEDIUM, "HARD": HARD}
