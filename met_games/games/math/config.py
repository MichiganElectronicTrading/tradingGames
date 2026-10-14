"""Mental Math configuration: modes, difficulties and the Custom settings."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from met_games.games.math.problems import EASY, FAMILIES, HARD, LEVELS, MEDIUM

SPRINT, SURVIVAL, ZETAMAC, OPTIVER, DRILL, DAILY = "sprint", "survival", "zetamac", "optiver", "drill", "daily"
CHAIN, ESTIMATE, FLOW, PROB_DRILL = "chain", "estimate", "flow", "prob"
MODES = (SPRINT, SURVIVAL, CHAIN, ESTIMATE, ZETAMAC, OPTIVER, FLOW, PROB_DRILL)  # the CLI's --mode choices
MODE_LABELS = {SPRINT: "SPRINT", SURVIVAL: "SURVIVAL", CHAIN: "CHAIN", ESTIMATE: "ESTIMATE", ZETAMAC: "ZETAMAC",
               OPTIVER: "OPTIVER-STYLE", FLOW: "FLOW-STYLE", PROB_DRILL: "PROBABILITY DRILL", DRILL: "DRILL",
               DAILY: "DAILY"}
CUSTOM, ADAPTIVE = "custom", "adaptive"
DIFFICULTIES = (EASY, MEDIUM, HARD, CUSTOM, ADAPTIVE)
STANDARD = "standard"  # Zetamac and Optiver-style have one fixed format
FIXED_FORMAT = (ZETAMAC, OPTIVER, FLOW)
# The difficulty pills each mode offers (fixed-format modes: none)
MODE_DIFFICULTIES = {SPRINT: DIFFICULTIES, SURVIVAL: DIFFICULTIES, CHAIN: (EASY, MEDIUM, HARD, CUSTOM),
                     ESTIMATE: (EASY, MEDIUM, HARD), ZETAMAC: (), OPTIVER: (), FLOW: (),
                     PROB_DRILL: (EASY, MEDIUM, HARD, ADAPTIVE), DRILL: DIFFICULTIES, DAILY: (MEDIUM,)}

SPRINT_S = 120
DURATION_RANGE = (30, 300)
# Survival: seconds added per correct answer at the start (Custom edits it); the floor is 1s everywhere.
SURVIVAL_BONUS_MS = {EASY: 10_000, MEDIUM: 8_000, HARD: 6_000}
BONUS_RANGE_MS = (1_000, 20_000)
SURVIVAL_FLOOR_MS = 1_000
# Chain Custom: the step clock and which operations it may use (± always on: it keeps every chain alive)
PM, TIMES, DIVIDE, PERCENT = "pm", "mul", "div", "pct"
CHAIN_OPS = (PM, TIMES, DIVIDE, PERCENT)
CHAIN_STEP_RANGE = (5, 20)


@dataclass(frozen=True)
class MathConfig:
    mode: str = SPRINT
    difficulty: str = MEDIUM  # easy | medium | hard | custom | adaptive (Sprint, Survival)
    duration_s: int = SPRINT_S  # Sprint only
    families: tuple[str, ...] = FAMILIES  # the problem mix (at least one)
    levels: tuple[tuple[str, str], ...] = ()  # Custom: per-family difficulty
    weights: tuple[tuple[str, int], ...] = ()  # Custom: per-family weight (default 1 each)
    bonus_ms: int | None = None  # Custom Survival: the starting bonus (default MEDIUM's)
    step_s: int | None = None  # Custom Chain: the per-step clock (default MEDIUM's)
    ops: tuple[str, ...] = CHAIN_OPS  # Custom Chain: the operations it may use
    seed: int | None = None

    def errors(self) -> list[str]:
        errs = []
        if self.mode not in (*MODES, DRILL, DAILY):
            errs.append("unknown mode")
        if self.difficulty not in DIFFICULTIES:
            errs.append("difficulty must be easy, medium, hard, custom or adaptive")
        elif (self.difficulty == ADAPTIVE or self.mode not in FIXED_FORMAT) and \
                self.difficulty not in MODE_DIFFICULTIES.get(self.mode, DIFFICULTIES):
            errs.append(f"{self.mode} has no {self.difficulty} difficulty"
                        + (" (adaptive is for sprint, survival and the probability drill)"
                           if self.difficulty == ADAPTIVE else ""))
        if not DURATION_RANGE[0] <= self.duration_s <= DURATION_RANGE[1]:
            errs.append("duration must be 0:30–5:00")
        if not self.families or any(f not in FAMILIES for f in self.families):
            errs.append("pick at least one problem family")
        if any(lv not in LEVELS for _, lv in self.levels):
            errs.append("family difficulty must be easy, medium or hard")
        if any(not 1 <= w <= 5 for _, w in self.weights):
            errs.append("weights must be 1–5")
        bonus, _ = self.survival_bonus()
        if not BONUS_RANGE_MS[0] <= bonus <= BONUS_RANGE_MS[1]:
            errs.append("survival bonus must be 1–20s")
        if self.step_s is not None and not CHAIN_STEP_RANGE[0] <= self.step_s <= CHAIN_STEP_RANGE[1]:
            errs.append("step clock must be 5–20s")
        if PM not in self.ops or any(o not in CHAIN_OPS for o in self.ops):
            errs.append("± stays on in a chain")
        return errs

    def validate(self) -> None:
        errs = self.errors()
        if errs:
            raise ValueError("; ".join(errs))

    def replace(self, **changes: Any) -> MathConfig:
        return replace(self, **changes)

    def level_map(self) -> dict[str, str]:
        default = self.difficulty if self.difficulty in LEVELS else MEDIUM  # adaptive runs pick levels per track
        custom = dict(self.levels) if self.difficulty == CUSTOM else {}
        return {f: custom.get(f, default) for f in FAMILIES}

    def survival_bonus(self) -> tuple[int, int]:
        """(starting bonus, floor) in ms: EASY 10s · MEDIUM 8s · HARD 6s, Custom its own (or MEDIUM's); floor 1s."""
        if self.difficulty != CUSTOM or self.bonus_ms is None:
            bonus = SURVIVAL_BONUS_MS.get(self.difficulty, SURVIVAL_BONUS_MS[MEDIUM])
        else:
            bonus = self.bonus_ms
        return bonus, SURVIVAL_FLOOR_MS

    def weight_map(self) -> dict[str, int]:
        return dict(self.weights) if self.difficulty == CUSTOM else {}

    @property
    def board(self) -> str:
        """The difficulty a run's bests and history are filed under."""
        return STANDARD if self.mode in FIXED_FORMAT else self.difficulty

