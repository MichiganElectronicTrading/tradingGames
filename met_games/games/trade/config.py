"""Trading Game configuration: TradeConfig and the EASY/MEDIUM/HARD presets.

TradeConfig is a CardConfig, so the deal (card counts, face-up range, events) and its checks are
Card's. Some inherited fields take a trading-game meaning (the properties below name them):

    rounds         → hands per session
    timer_s        → your take timer
    spread         → the computer traders' quote width
    sizing         → your quote size: "fixed" (5 per side) or "choose" (1–10)
    mid_round_flip → a hidden card flips face up between turns

quote_noise_sd and stale_quotes are unused: the computer traders quote deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from met_games.games.card.config import CardConfig
from met_games.games.card.events import EVENT_KEYS
from met_games.games.sumgame.config import events_label, span

PEEKS = ("one", "all")  # one random trader peeks, or all three do

# Card's messages, renamed to what the fields mean here.
_RENAMED = {"rounds": "hands", "timer": "take timer", "spread": "trader width"}


@dataclass(frozen=True)
class TradeConfig(CardConfig):
    FIXED_SIZE: ClassVar[int] = 5  # your quote size when sizing is "fixed"
    SIZE_MAX: ClassVar[int] = 10  # largest quote size when sizing is "choose"
    TIMER_MAX: ClassVar[int] = 120

    timer_s: int = 30
    quote_timer_s: int = 45
    width_min: int = 2
    width_max: int = 6
    peeks: str = "one"
    learn_rate: float = 0.0

    @property
    def hands(self) -> int:
        return self.rounds

    @property
    def take_timer_s(self) -> int:
        return self.timer_s

    @property
    def trader_width(self) -> int:
        return int(self.spread)

    @property
    def flip_between_turns(self) -> bool:
        return self.mid_round_flip

    def errors(self) -> list[str]:
        errs = []
        for e in super().errors():
            first, _, rest = e.partition(" ")
            errs.append(f"{_RENAMED[first]} {rest}" if first in _RENAMED else e)
        if not 5 <= self.quote_timer_s <= self.TIMER_MAX:
            errs.append(f"quote timer must be 5–{self.TIMER_MAX}s")
        if not 1 <= self.width_min <= self.width_max <= self.SPREAD_MAX:
            errs.append(f"allowed width must be 1–{self.SPREAD_MAX} with min ≤ max")
        if self.peeks not in PEEKS:
            errs.append("peeks must be one or all")
        if not 0 <= self.learn_rate <= 1:
            errs.append("learn rate must be 0–1")
        return errs

    def summary(self) -> dict[str, str]:
        """Rows for the lobby's MODES table."""
        return {
            "cards": span(self.n_min, self.n_max),
            "face up": span(self.face_up_min, self.face_up_max),
            "hands": str(self.hands),
            "your quote timer": f"{self.quote_timer_s}s",
            "your take timer": f"{self.take_timer_s}s",
            "your allowed width": span(self.width_min, self.width_max),
            "your quote size": size_label(self),
            "trader width": str(self.trader_width),
            "peeks": peeks_label(self.peeks),
            "flip between turns": "yes" if self.flip_between_turns else "no",
            "learn_rate": f"{self.learn_rate:g}",
            "events": events_label(self).replace("every round", "every hand").replace("of rounds", "of hands"),
            "budget": f"${self.budget}",
        }


def size_label(cfg: TradeConfig) -> str:
    return f"{cfg.FIXED_SIZE} fixed" if cfg.sizing == "fixed" else f"1–{cfg.SIZE_MAX}"


def peeks_label(peeks: str) -> str:
    return "1 trader" if peeks == "one" else "all 3"


EASY = TradeConfig()
MEDIUM = TradeConfig(
    n_cards_min=5, n_cards_max=5, face_up_max=2, quote_timer_s=30, timer_s=20, width_min=1, width_max=4,
    sizing="choose", spread=2, peeks="all",
)
HARD = TradeConfig(
    n_cards_min=6, n_cards_max=8, face_up_min=1, face_up_max=3, rounds=6, quote_timer_s=15, timer_s=10,
    width_min=1, width_max=3, sizing="choose", spread=2, peeks="all", mid_round_flip=True, learn_rate=0.25,
    event_freq=1.0, enabled_events=EVENT_KEYS,
)

PRESETS: dict[str, TradeConfig] = {"EASY": EASY, "MEDIUM": MEDIUM, "HARD": HARD}
