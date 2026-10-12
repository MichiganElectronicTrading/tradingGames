"""Mental Math configuration: modes, difficulties and the Custom settings."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from met_games.games.math.problems import EASY, FAMILIES, HARD, LEVELS, MEDIUM

SPRINT, SURVIVAL, ZETAMAC, OPTIVER, DRILL, DAILY = "sprint", "survival", "zetamac", "optiver", "drill", "daily"
MODES = (SPRINT, SURVIVAL, ZETAMAC, OPTIVER)  # the CLI's --mode choices
MODE_LABELS = {SPRINT: "SPRINT", SURVIVAL: "SURVIVAL", ZETAMAC: "ZETAMAC", OPTIVER: "OPTIVER-STYLE",
               DRILL: "DRILL", DAILY: "DAILY"}
CUSTOM = "custom"
DIFFICULTIES = (EASY, MEDIUM, HARD, CUSTOM)
STANDARD = "standard"  # Zetamac and Optiver-style have one fixed format
FIXED_FORMAT = (ZETAMAC, OPTIVER)

SPRINT_S = 120
DURATION_RANGE = (30, 300)
# Survival: seconds added per correct answer at the start; the floor is half of it. Custom edits both.
SURVIVAL_BONUS_MS = {EASY: 10_000, MEDIUM: 8_000, HARD: 6_000}
BONUS_RANGE_MS = (1_000, 20_000)
FLOOR_MIN_MS = 500


@dataclass(frozen=True)
class MathConfig:
    mode: str = SPRINT
    difficulty: str = MEDIUM  # easy | medium | hard | custom
    duration_s: int = SPRINT_S  # Sprint only
    families: tuple[str, ...] = FAMILIES  # the problem mix (at least one)
    levels: tuple[tuple[str, str], ...] = ()  # Custom: per-family difficulty
    weights: tuple[tuple[str, int], ...] = ()  # Custom: per-family weight (default 1 each)
    bonus_ms: int | None = None  # Custom Survival: the starting bonus (default MEDIUM's)
    floor_ms: int | None = None  # Custom Survival: the bonus floor (default half the starting bonus)
    seed: int | None = None

    def errors(self) -> list[str]:
        errs = []
        if self.mode not in (*MODES, DRILL, DAILY):
            errs.append("unknown mode")
        if self.difficulty not in DIFFICULTIES:
            errs.append("difficulty must be easy, medium, hard or custom")
        if not DURATION_RANGE[0] <= self.duration_s <= DURATION_RANGE[1]:
            errs.append("duration must be 0:30–5:00")
        if not self.families or any(f not in FAMILIES for f in self.families):
            errs.append("pick at least one problem family")
        if any(lv not in LEVELS for _, lv in self.levels):
            errs.append("family difficulty must be easy, medium or hard")
        if any(not 1 <= w <= 5 for _, w in self.weights):
            errs.append("weights must be 1–5")
        bonus, floor = self.survival_bonus()
        if not BONUS_RANGE_MS[0] <= bonus <= BONUS_RANGE_MS[1]:
            errs.append("survival bonus must be 1–20s")
        if not FLOOR_MIN_MS <= floor <= bonus:
            errs.append("survival floor must be 0.5s up to the bonus")
        return errs

    def validate(self) -> None:
        errs = self.errors()
        if errs:
            raise ValueError("; ".join(errs))

    def replace(self, **changes: Any) -> MathConfig:
        return replace(self, **changes)

    def level_map(self) -> dict[str, str]:
        default = self.difficulty if self.difficulty in LEVELS else MEDIUM
        custom = dict(self.levels) if self.difficulty == CUSTOM else {}
        return {f: custom.get(f, default) for f in FAMILIES}

    def survival_bonus(self) -> tuple[int, int]:
        """(starting bonus, floor) in ms: EASY 10s/5s · MEDIUM 8s/4s · HARD 6s/3s; Custom its own (or MEDIUM's)."""
        if self.difficulty != CUSTOM or self.bonus_ms is None:
            bonus = SURVIVAL_BONUS_MS.get(self.difficulty, SURVIVAL_BONUS_MS[MEDIUM])
        else:
            bonus = self.bonus_ms
        floor = self.floor_ms if self.difficulty == CUSTOM and self.floor_ms is not None else bonus // 2
        return bonus, floor

    def weight_map(self) -> dict[str, int]:
        return dict(self.weights) if self.difficulty == CUSTOM else {}

    @property
    def board(self) -> str:
        """The difficulty a run's bests and history are filed under."""
        return STANDARD if self.mode in FIXED_FORMAT else self.difficulty

