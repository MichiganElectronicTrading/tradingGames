"""Dice market events. Each event is six equally likely face values replacing [1, 2, 3, 4, 5, 6];
it applies to face-up and hidden dice alike."""

from __future__ import annotations

from dataclasses import dataclass

STANDARD = (1, 2, 3, 4, 5, 6)


REMAP, VALUE = "remap", "value"  # display modes: rolled face + struck-through value, or the value itself


@dataclass(frozen=True)
class DiceEvent:
    key: str
    name: str
    rule: str
    faces: tuple[int, ...] = STANDARD  # value of a die showing 1..6 under this event
    display: str = REMAP  # how a die is drawn under this event (display only; values come from `faces`)


EVENTS: dict[str, DiceEvent] = {
    e.key: e
    for e in (
        DiceEvent("high_only", "HIGH ONLY", "only 5s and 6s this round", (5, 5, 5, 6, 6, 6), VALUE),
        DiceEvent("one_is_seven", "ONE IS SEVEN", "a 1 is worth 7 this round", (7, 2, 3, 4, 5, 6)),
        DiceEvent("six_is_zero", "SIX IS ZERO", "6s count as 0 this round", (1, 2, 3, 4, 5, 0)),
        DiceEvent("evens_double", "EVENS DOUBLE", "even dice count double", (1, 4, 3, 8, 5, 12)),
        DiceEvent("odds_negative", "ODDS NEGATIVE", "odd dice count negative", (-1, 2, -3, 4, -5, 6)),
        DiceEvent("double_hidden", "DOUBLE DOWN", "one hidden die counts double"),
    )
}
EVENT_KEYS: tuple[str, ...] = tuple(EVENTS)


def faces(event: str | None) -> tuple[int, ...]:
    return EVENTS[event].faces if event else STANDARD


def die_value(face: int, event: str | None) -> int:
    return faces(event)[face - 1]


def display_mode(event: str | None) -> str:
    return EVENTS[event].display if event else REMAP
