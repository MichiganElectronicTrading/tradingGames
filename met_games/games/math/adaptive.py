"""Adaptive difficulty: a level (1–10) per skill track, moved by how you answer. Pure Python, no Textual.

Per track, per run: up one level after 3 correct answers in a row at the current level, each within the track's
target time; down one after a miss or skip, or after 2 correct answers in a row slower than twice the target. Any
level change resets both counters. Levels persist in ~/.met_games/math_levels.json with one snapshot per day
(the last 60 days), which is what MY STATS compares against for its 7-day arrows.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from met_games import storage
from met_games.games.math.ladder import (
    ADDSUB,
    ANCHOR_LEVEL,
    DEC,
    DESK_TRACK,
    DIV,
    FAMILY_TRACKS,
    FRAC,
    LEVEL_MAX,
    LEVEL_MIN,
    ALL_TRACKS,
    MUL,
    PCT_TRACK,
    PROB_TRACK,
    SUBTYPE_TRACK,
    TRACKS,
    make_at,
)
from met_games.games.math.problems import EASY, FAMILIES, HARD, MEDIUM, PROB, Problem

TARGET_MS = {ADDSUB: 2_500, MUL: 3_000, DIV: 3_500, DEC: 4_500, FRAC: 5_000, PCT_TRACK: 5_000, DESK_TRACK: 8_000}
PROB_TARGET_MS = 15_000  # the Probability drill's track
TARGETS = {**TARGET_MS, PROB_TRACK: PROB_TARGET_MS}
UP_AFTER = 3  # correct answers in a row, each within the target, to go up
SLOW_FACTOR = 2  # slower than this × the target is "slow"
DOWN_AFTER_SLOW = 2  # slow correct answers in a row to go down
START_LEVEL = 3  # EASY
SEED_MIN = 20  # logged problems at a difficulty before history can seed a track there
SEED_ACCURACY = Fraction(4, 5)
LEVELS_FILE = "math_levels.json"
KEEP_DAYS = 60
WEEK_DAYS = 7


# ── the rule ────────────────────────────────────────────────────────────────


@dataclass
class TrackState:
    level: int
    fast: int = 0  # correct answers in a row within the target
    slow: int = 0  # correct answers in a row slower than 2× the target


def outcome_change(state: TrackState, target_ms: int, correct: bool, ms: int) -> int:
    """Apply one answer to a track; returns the level change (−1, 0 or +1). At L1 / L10 a firing rule changes
    nothing but still resets the counters."""
    if not correct:
        move = -1
    elif ms <= target_ms:
        state.fast, state.slow = state.fast + 1, 0
        move = 1 if state.fast >= UP_AFTER else 0
    elif ms > SLOW_FACTOR * target_ms:
        state.fast, state.slow = 0, state.slow + 1
        move = -1 if state.slow >= DOWN_AFTER_SLOW else 0
    else:  # correct, between the target and 2× it: breaks both runs
        state.fast = state.slow = 0
        move = 0
    if not move:
        return 0
    old = state.level
    state.level = max(LEVEL_MIN, min(LEVEL_MAX, old + move))
    state.fast = state.slow = 0
    return state.level - old


class Ladder:
    """One run's levels: every track it holds (the Sprint / Survival seven, or the Probability drill's one) starts
    where it was saved and moves by the rule."""

    def __init__(self, levels: dict[str, int], tracks: tuple[str, ...] = TRACKS) -> None:
        self.start = {t: levels.get(t, START_LEVEL) for t in tracks}
        self.tracks = {t: TrackState(self.start[t]) for t in tracks}
        self.changes: list[tuple[str, int, int]] = []  # (track, from, to), in order

    def level(self, track: str) -> int:
        return self.tracks[track].level

    @property
    def levels(self) -> dict[str, int]:
        return {t: s.level for t, s in self.tracks.items()}

    def record(self, track: str, correct: bool, ms: int) -> int:
        state = self.tracks[track]
        old = state.level
        move = outcome_change(state, TARGETS[track], correct, ms)
        if move:
            self.changes.append((track, old, state.level))
        return move


class AdaptiveStream:
    """Problems for an adaptive run: families from shuffled bags (the toggles still apply), a track drawn evenly
    within the family, at that track's current level. `tracks` restricts it to those tracks (the focus drill)."""

    def __init__(self, seed: int | str, levels: dict[str, int], families: tuple[str, ...] = FAMILIES,
                 tracks: tuple[str, ...] | None = None) -> None:
        self.rng = random.Random(seed)
        self.ladder = Ladder(levels)
        self.tracks = tracks
        self.entries: list[str] = list(tracks) if tracks else list(families)
        if not self.entries:
            raise ValueError("pick at least one family")
        self.bag: list[str] = []

    def next(self) -> Problem:
        if not self.bag:
            self.bag = list(self.entries)
            self.rng.shuffle(self.bag)
        entry = self.bag.pop()
        if self.tracks:
            track = entry
        else:
            options = FAMILY_TRACKS[entry]
            track = options[0] if len(options) == 1 else self.rng.choice(options)
        return make_at(self.rng, track, self.ladder.level(track))

    def observe(self, attempt: Any) -> None:
        """Called by the run after every answer or skip, before the next problem is drawn."""
        self.ladder.record(SUBTYPE_TRACK[attempt.problem.subtype], attempt.correct, attempt.ms)


# ── seeding from history ────────────────────────────────────────────────────


def record_track(record: dict[str, Any]) -> str | None:
    """A logged problem's track for seeding: its subtype's, or prob for the probability family."""
    return PROB_TRACK if record.get("family") == PROB else SUBTYPE_TRACK.get(record.get("subtype"))


def seed_level(history: list[dict[str, Any]], track: str) -> int:
    """The highest anchor (L9 / L6 / L3) with ≥ 80% accuracy over ≥ 20 logged problems on this track at that
    difficulty; otherwise L3."""
    for anchor in (HARD, MEDIUM, EASY):
        mine = [r for r in history if r.get("level") == anchor and record_track(r) == track]
        right = sum(r.get("outcome") == "correct" for r in mine)
        if len(mine) >= SEED_MIN and Fraction(right, len(mine)) >= SEED_ACCURACY:
            return ANCHOR_LEVEL[anchor]
    return START_LEVEL


# ── persistence ─────────────────────────────────────────────────────────────


def load_state() -> dict[str, Any]:
    data = storage.read_json(LEVELS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    levels = data.get("levels") if isinstance(data.get("levels"), dict) else {}
    snaps = data.get("snapshots") if isinstance(data.get("snapshots"), dict) else {}
    return {"levels": {t: int(v) for t, v in levels.items() if t in ALL_TRACKS}, "snapshots": snaps}


def prune(snapshots: dict[str, Any], today: date) -> dict[str, Any]:
    """Only the last 60 days of snapshots (today included)."""
    oldest = (today - timedelta(days=KEEP_DAYS - 1)).isoformat()
    return {d: v for d, v in sorted(snapshots.items()) if d >= oldest}


def save_levels(levels: dict[str, int], today: date | None = None) -> None:
    """These tracks' levels (the others keep theirs), plus today's snapshot of every level (one per day: a later
    save overwrites it)."""
    today = today or date.today()
    state = load_state()
    state["levels"].update({t: levels[t] for t in ALL_TRACKS if t in levels})
    state["snapshots"][today.isoformat()] = dict(state["levels"])
    state["snapshots"] = prune(state["snapshots"], today)
    storage.write_json(LEVELS_FILE, state)


def load_levels(history: list[dict[str, Any]] | None = None, today: date | None = None,
                tracks: tuple[str, ...] = TRACKS) -> dict[str, int]:
    """These tracks' levels (default: the Sprint / Survival seven). A track never saved before is seeded from history
    once, and saved."""
    state = load_state()
    levels = {t: v for t, v in state["levels"].items() if t in tracks}
    missing = [t for t in tracks if t not in levels]
    if missing:
        if history is None:
            from met_games.games.math.history import load_history

            history = load_history()
        for t in missing:
            levels[t] = seed_level(history, t)
        save_levels(levels, today)
    return levels


def stored_levels() -> dict[str, int] | None:
    """The saved levels without seeding anything (None before the first adaptive run)."""
    levels = load_state()["levels"]
    return levels if levels else None


def week_ago(today: date | None = None) -> dict[str, int] | None:
    """The snapshot to compare against: the latest one at least 7 days old, else the oldest there is."""
    today = today or date.today()
    snaps = load_state()["snapshots"]
    if not snaps:
        return None
    cutoff = (today - timedelta(days=WEEK_DAYS)).isoformat()
    older = [d for d in snaps if d <= cutoff]
    return snaps[max(older)] if older else snaps[min(snaps)]


def arrow(now: int, then: int | None) -> str:
    if then is None or now == then:
        return "·"
    return "▲" if now > then else "▼"
