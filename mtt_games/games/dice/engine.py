"""Dice Game engine: the dice source (roll, values, fair value, range) on top of the shared core.

Every die is an independent fair roll, so a hidden die's expected value is the mean of the six
(event-adjusted) faces no matter what is face up.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from mtt_games.games.dice.config import PRESETS, DiceConfig
from mtt_games.games.dice.events import EVENTS, die_value, faces
from mtt_games.games.sumgame.engine import Round, SumSession
from mtt_games.games.sumgame.source import DOUBLE_HIDDEN, Market, Source


@dataclass(frozen=True)
class Die:
    face: int  # 1..6 as rolled

    def __str__(self) -> str:
        return str(self.face)


def fair_and_range(
    up_values: Sequence[int], face_values: Sequence[int], k: int, double_hidden: bool = False
) -> tuple[float, int, int]:
    """fair = up + k·m, min = up + k·lo, max = up + k·hi over the six face values;
    double_hidden counts one more hidden draw (k+1)."""
    s = sum(up_values)
    draws = k + 1 if double_hidden and k > 0 else k
    mean = math.fsum(face_values) / len(face_values)
    return s + draws * mean, s + draws * min(face_values), s + draws * max(face_values)


class DiceSource(Source):
    key = "dice"
    title = "DICE GAME"
    item = "die"
    mean_label = "face mean"
    config_cls = DiceConfig
    presets = PRESETS
    events = EVENTS

    def deal(self, rng: random.Random, n: int, event: str | None) -> list[Die]:
        return [Die(rng.randint(1, 6)) for _ in range(n)]

    def value(self, item: Die, event: str | None) -> int:
        return die_value(item.face, event)

    def market(self, up_items: Sequence[Die], event: str | None, hidden: int) -> Market:
        face_values = faces(event)
        up = [die_value(d.face, event) for d in up_items]
        double = event == DOUBLE_HIDDEN and hidden > 0
        fair, lo, hi = fair_and_range(up, face_values, hidden, double)
        return Market(sum(up), hidden, math.fsum(face_values) / 6, 6, double, fair, lo, hi)

    def settle_range(self, cfg: DiceConfig) -> tuple[int, int]:
        events: list[str | None] = [] if cfg.event_freq >= 1 and cfg.enabled_events else [None]
        if cfg.event_freq > 0:
            events += [e for e in cfg.enabled_events if e in EVENTS]
        lo, hi = math.inf, -math.inf
        for event in events:
            for n in range(max(2, min(cfg.n_min, cfg.n_max)), min(10, max(cfg.n_min, cfg.n_max)) + 1):
                double = event == DOUBLE_HIDDEN and cfg.face_up_min < n
                _, a, b = fair_and_range([], faces(event), n, double)
                lo, hi = min(lo, a), max(hi, b)
        return int(lo), int(hi)

    def explain_notes(self, m: Market) -> list[str]:
        notes = [
            f"face up {m.up_sum}: sum of the dice you could see",
            f"face mean {m.deck_mean:.2f}: average of the six equally likely faces — each hidden die is an "
            "independent roll, so the face-up dice tell you nothing about it",
        ]
        if m.double_hidden:
            notes.append("one hidden die counts twice, so there are k+1 hidden rolls")
        return notes

    def event_note(self, event: str) -> str:
        e = EVENTS[event]
        note = f"event {e.name}: {e.rule}"
        if event != DOUBLE_HIDDEN:
            note += f" — faces become {list(e.faces)} for every die, face up or hidden"
        return note

    def label(self, item: Die) -> str:
        return str(item.face)

    def flip_label(self, item: Die) -> str:
        return f"a {item.face}"


DICE = DiceSource()


class DiceRound(Round):
    SOURCE = DICE

    @property
    def dice(self) -> list[Any]:
        return self.items


class DiceSession(SumSession):
    ROUND = DiceRound
