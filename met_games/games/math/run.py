"""Mental Math runs on a millisecond clock: Sprint, Survival, Zetamac, Drill and the Daily (typed answers that lock
on equality), and Optiver-style (80 multiple-choice questions). Pure Python, no Textual.

The UI feeds real (or injected) time in with `advance_to(ms)`; nothing here reads a clock.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from met_games.games.math.adaptive import AdaptiveStream, Ladder, load_levels
from met_games.games.math.config import ADAPTIVE, DRILL, OPTIVER, SPRINT, STANDARD, SURVIVAL, ZETAMAC, MathConfig
from met_games.games.math.optiver import Question, optiver_questions
from met_games.games.math.problems import ALLOWED, Problem, ProblemStream, ZetamacStream, accepts

CORRECT, SKIPPED, WRONG = "correct", "skipped", "wrong"
COMBO_STEP, COMBO_CAP = Fraction(1, 10), Fraction(3)
SURVIVAL_START_MS = 30_000
SURVIVAL_STEP_MS, SURVIVAL_EVERY = 500, 5
SKIP_PENALTY_MS = 5_000
ZETAMAC_MS = 120_000
OPTIVER_MS = 480_000
DRILL_MS = 120_000
MAX_TYPED = 12


def combo(streak: int) -> Fraction:
    """×(1 + 0.1 × streak), capped at ×3."""
    return min(1 + COMBO_STEP * streak, COMBO_CAP)


def points(base: int, streak_before: int) -> int:
    """round(base × combo), with the streak from before this answer. (Every base × combo is a whole number.)"""
    return round(base * combo(streak_before))


def survival_bonus_ms(correct_before: int, start_ms: int, floor_ms: int) -> int:
    """`start_ms` per correct; every 5 correct the bonus drops 0.5s, never below `floor_ms`."""
    return max(floor_ms, start_ms - SURVIVAL_STEP_MS * (correct_before // SURVIVAL_EVERY))


@dataclass(frozen=True)
class Attempt:
    problem: Problem
    outcome: str  # correct | skipped | wrong
    ms: int  # time from the problem showing to the answer / skip
    points: int
    streak_before: int
    given: str = ""  # what you answered (Optiver-style: the option you picked)

    @property
    def correct(self) -> bool:
        return self.outcome == CORRECT


class ListStream:
    """A fixed list of problems (the daily's 200)."""

    def __init__(self, problems: Iterable[Problem]) -> None:
        self.problems = list(problems)
        self.i = 0

    def next(self) -> Problem | None:
        if self.i >= len(self.problems):
            return None
        self.i += 1
        return self.problems[self.i - 1]


class Run:
    """A typed-answer run. Sprint/Zetamac/Drill/Daily end when their time is up; Survival when its bank hits 0."""

    def __init__(self, mode: str, stream, *, duration_ms: int, board: str, seed: int | str,
                 scored: bool = True, config: MathConfig | None = None) -> None:
        self.mode, self.stream, self.board, self.seed, self.scored = mode, stream, board, seed, scored
        self.config = config
        self.ladder: Ladder | None = getattr(stream, "ladder", None)  # adaptive runs: the levels, moving
        self.day = None  # the daily's date
        self.ended_early = False  # ended before its clock ran out (Ctrl+E, or leaving the daily)
        self.focus: str | None = None  # a focus drill's track
        self.survival = mode == SURVIVAL
        self.bonus_start_ms, self.bonus_floor_ms = (config or MathConfig(mode=mode)).survival_bonus()
        self.bank_ms = SURVIVAL_START_MS if self.survival else duration_ms
        self.duration_ms = self.bank_ms
        self.now = 0
        self.shown_at = 0
        self.typed = ""
        self.attempts: list[Attempt] = []
        self.streak = 0
        self.best_streak = 0
        self.best_combo = Fraction(1)
        self.over = False
        self.problem: Problem | None = stream.next()
        if self.problem is None:
            self.over = True

    # ── clock ───────────────────────────────────────────────────────────────

    @property
    def time_left_ms(self) -> int:
        return max(0, self.bank_ms - self.now)

    @property
    def bonus_ms(self) -> int:
        """Survival: what the next correct answer adds."""
        return survival_bonus_ms(self.correct, self.bonus_start_ms, self.bonus_floor_ms)

    def advance_to(self, ms: int) -> None:
        if self.over or ms <= self.now:
            return
        self.now = ms
        if self.time_left_ms == 0:
            self.end()

    def end(self) -> None:
        """Time's up (or you quit): the problem on screen isn't scored or logged."""
        self.over = True

    # ── input ───────────────────────────────────────────────────────────────

    def type(self, ch: str) -> Attempt | None:
        """Add one character; returns the Attempt if it locked the answer."""
        if self.over or ch not in ALLOWED or len(self.typed) >= MAX_TYPED:
            return None
        self.typed += ch
        return self._resolve(CORRECT) if accepts(self.problem, self.typed) else None

    def backspace(self) -> None:
        if not self.over:
            self.typed = self.typed[:-1]

    def skip(self) -> Attempt | None:
        return None if self.over else self._resolve(SKIPPED)

    def _resolve(self, outcome: str) -> Attempt:
        p = self.problem
        streak = self.streak
        pts = points(p.base, streak) if outcome == CORRECT and self.scored else 0
        attempt = Attempt(p, outcome, self.now - self.shown_at, pts, streak, self.typed)
        if self.survival:
            self.bank_ms += self.bonus_ms if outcome == CORRECT else -SKIP_PENALTY_MS
        self.attempts.append(attempt)
        observe = getattr(self.stream, "observe", None)  # adaptive: the level moves before the next problem
        if observe is not None:
            observe(attempt)
        if outcome == CORRECT:
            self.best_combo = max(self.best_combo, combo(streak))
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
        else:
            self.streak = 0
        self.problem, self.typed, self.shown_at = self.stream.next(), "", self.now
        if self.problem is None or self.time_left_ms == 0:
            self.end()
        return attempt

    # ── score ───────────────────────────────────────────────────────────────

    @property
    def correct(self) -> int:
        return sum(a.correct for a in self.attempts)

    @property
    def skipped(self) -> int:
        return sum(a.outcome == SKIPPED for a in self.attempts)

    @property
    def wrong(self) -> int:
        return 0

    @property
    def points(self) -> int:
        return sum(a.points for a in self.attempts)

    @property
    def combo(self) -> Fraction:
        return combo(self.streak)


class OptiverRun:
    """80 multiple-choice questions in 8:00. +1 right, −1 wrong, 0 skipped; no going back."""

    def __init__(self, seed: int | str, questions: list[Question] | None = None) -> None:
        self.mode, self.board, self.seed, self.scored = OPTIVER, STANDARD, seed, False
        self.config = None
        self.questions = questions if questions is not None else optiver_questions(seed)
        self.duration_ms = OPTIVER_MS
        self.now = 0
        self.shown_at = 0
        self.i = 0
        self.attempts: list[Attempt] = []
        self.ended_early = False
        self.over = False
        self.best_combo = Fraction(1)

    @property
    def question(self) -> Question | None:
        return self.questions[self.i] if self.i < len(self.questions) else None

    @property
    def time_left_ms(self) -> int:
        return max(0, self.duration_ms - self.now)

    def advance_to(self, ms: int) -> None:
        if self.over or ms <= self.now:
            return
        self.now = ms
        if self.time_left_ms == 0:
            self.end()

    def end(self) -> None:
        self.over = True

    def answer(self, option: int) -> Attempt | None:
        """Pick option 0–3; moves straight on."""
        if self.over or not 0 <= option < len(self.question.options):
            return None
        q = self.question
        return self._resolve(CORRECT if option == q.correct else WRONG, q.options[option])

    def skip(self) -> Attempt | None:
        return None if self.over else self._resolve(SKIPPED, "")

    def _resolve(self, outcome: str, given: str) -> Attempt:
        attempt = Attempt(self.question.problem, outcome, self.now - self.shown_at, 0, 0, given)
        self.attempts.append(attempt)
        self.i += 1
        self.shown_at = self.now
        if self.i >= len(self.questions):
            self.end()
        return attempt

    @property
    def answered(self) -> int:
        return len(self.attempts)

    @property
    def correct(self) -> int:
        return sum(a.correct for a in self.attempts)

    @property
    def wrong(self) -> int:
        return sum(a.outcome == WRONG for a in self.attempts)

    @property
    def skipped(self) -> int:
        return sum(a.outcome == SKIPPED for a in self.attempts)

    @property
    def net(self) -> int:
        return self.correct - self.wrong

    @property
    def points(self) -> int:
        return 0

    def pace(self) -> tuple[Fraction | None, Fraction | None]:
        """(your average seconds per question so far, seconds per question needed to finish the rest)."""
        avg = Fraction(self.now, 1000 * self.answered) if self.answered else None
        left = len(self.questions) - self.answered
        need = Fraction(self.time_left_ms, 1000 * left) if left else None
        return avg, need


def new_run(config: MathConfig, seed: int, pool: list[tuple[str, str]] | None = None,
            levels: dict[str, int] | None = None) -> Run | OptiverRun:
    """A run for `config` (Sprint, Survival, Zetamac, Optiver-style or Drill) on this seed. Adaptive runs start
    from `levels` (default: the saved ones)."""
    config.validate()
    if config.mode == OPTIVER:
        return OptiverRun(seed)
    if config.mode == ZETAMAC:
        return Run(ZETAMAC, ZetamacStream(seed), duration_ms=ZETAMAC_MS, board=STANDARD, seed=seed, scored=False,
                   config=config)
    if config.mode == DRILL:
        stream = ProblemStream(seed, levels=config.level_map(), pool=pool)
        return Run(DRILL, stream, duration_ms=DRILL_MS, board=config.board, seed=seed, config=config)
    if config.difficulty == ADAPTIVE:
        stream = AdaptiveStream(seed, load_levels() if levels is None else levels, config.families)
    else:
        stream = ProblemStream(seed, config.families, config.level_map(), config.weight_map())
    duration = config.duration_s * 1000 if config.mode == SPRINT else 0
    return Run(config.mode, stream, duration_ms=duration, board=config.board, seed=seed, config=config)


def new_drill(seed: int, pool: list[tuple[str, str, str]], board: str) -> Run:
    """D on the report: a 2:00 Sprint on the run's weakest subtypes, each at the difficulty it was seen at."""
    return Run(DRILL, ProblemStream(seed, pool=pool), duration_ms=DRILL_MS, board=board, seed=seed)


def new_focus_drill(seed: int, track: str, levels: dict[str, int] | None = None) -> Run:
    """F on MY STATS: a 2:00 adaptive Sprint on one track. Logged (and it moves your levels), never a best."""
    stream = AdaptiveStream(seed, load_levels() if levels is None else levels, tracks=(track,))
    run = Run(DRILL, stream, duration_ms=DRILL_MS, board=ADAPTIVE, seed=seed)
    run.focus = track
    return run


def new_seed() -> int:
    return random.SystemRandom().randrange(1, 1_000_000)

