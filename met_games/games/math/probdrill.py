"""The Probability drill: 20 prob questions in 10:00. Typed answers, Enter submits, S skips; right after each answer
you see ✓, or ✗ with the right answer, and why. EASY / MEDIUM / HARD, or ADAPTIVE on the prob track's level.
Pure Python, no Textual."""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from met_games.games.math.adaptive import Ladder, load_levels
from met_games.games.math.config import ADAPTIVE, PROB_DRILL, MathConfig
from met_games.games.math.ladder import PROB_TRACK
from met_games.games.math.prob import SUBTYPES, ProbProblem, diagnose, is_right, make_level, make_prob, readable
from met_games.games.math.problems import ALLOWED, PROB
from met_games.games.math.run import CORRECT, SKIPPED, WRONG

QUESTIONS = 20
PROB_MS = 600_000
MAX_TYPED = 14
KEYS = ALLOWED | {","}  # commas: counting answers like 2,598,960


@dataclass(frozen=True)
class Answer:
    problem: ProbProblem
    outcome: str  # correct | wrong | skipped
    given: str
    ms: int
    mistake: str | None  # the known mistake a wrong answer matched

    @property
    def correct(self) -> bool:
        return self.outcome == CORRECT


class ProbRun:
    def __init__(self, config: MathConfig, seed: int | str, levels: dict[str, int] | None = None) -> None:
        config.validate()
        self.mode, self.board, self.seed, self.config = PROB_DRILL, config.board, seed, config
        self.rng = random.Random(seed)
        self.adaptive = config.difficulty == ADAPTIVE
        self.ladder: Ladder | None = None
        if self.adaptive:
            start = load_levels(tracks=(PROB_TRACK,)) if levels is None else levels
            self.ladder = Ladder(start, tracks=(PROB_TRACK,))
        self.scored = False
        self.day = None
        self.focus = None
        self.ended_early = False
        self.answers: list[Answer] = []
        self.duration_ms = PROB_MS
        self.now = 0
        self.shown_at = 0
        self.typed = ""
        self.over = False
        self.best_combo = Fraction(1)
        self.problem: ProbProblem | None = self._draw()

    def _draw(self) -> ProbProblem:
        if self.ladder is not None:
            return make_level(self.rng, self.ladder.level(PROB_TRACK))
        return make_prob(self.rng, self.config.difficulty)

    @property
    def last(self) -> Answer | None:
        return self.answers[-1] if self.answers else None

    # ── clock ───────────────────────────────────────────────────────────────

    @property
    def time_left_ms(self) -> int:
        return max(0, PROB_MS - self.now)

    def advance_to(self, ms: int) -> None:
        if self.over or ms <= self.now:
            return
        self.now = ms
        if self.time_left_ms == 0:
            self.end()

    def end(self) -> None:
        self.over = True

    # ── input ───────────────────────────────────────────────────────────────

    def type(self, ch: str) -> None:
        if not self.over and ch in KEYS and len(self.typed) < MAX_TYPED:
            self.typed += ch

    def backspace(self) -> None:
        if not self.over:
            self.typed = self.typed[:-1]

    def submit(self) -> Answer | None:
        """Enter: mark what's typed. Nothing, or not an answer of the right kind (not a number; on a counting question,
        not a whole number), and nothing happens."""
        if self.over or not readable(self.problem, self.typed):
            return None
        p = self.problem
        if is_right(p, self.typed):
            return self._record(CORRECT, None)
        return self._record(WRONG, diagnose(p, self.typed))

    def skip(self) -> Answer | None:
        return None if self.over else self._record(SKIPPED, None)

    def _record(self, outcome: str, mistake: str | None) -> Answer:
        answer = Answer(self.problem, outcome, self.typed if outcome != SKIPPED else "", self.now - self.shown_at,
                        mistake)
        self.answers.append(answer)
        if self.ladder is not None:
            self.ladder.record(PROB_TRACK, outcome == CORRECT, answer.ms)
        self.typed, self.shown_at = "", self.now
        if len(self.answers) >= QUESTIONS:
            self.problem = None
            self.end()
        else:
            self.problem = self._draw()
        return answer

    # ── score ───────────────────────────────────────────────────────────────

    @property
    def answered(self) -> int:
        return len(self.answers)

    @property
    def correct(self) -> int:
        return sum(a.outcome == CORRECT for a in self.answers)

    @property
    def wrong(self) -> int:
        return sum(a.outcome == WRONG for a in self.answers)

    @property
    def skipped(self) -> int:
        return sum(a.outcome == SKIPPED for a in self.answers)

    @property
    def points(self) -> int:
        return 0

    def by_subtype(self) -> list[tuple[str, int, int]]:
        """(subtype, right, seen) for every subtype seen, in family order."""
        out = []
        for sub in SUBTYPES:
            mine = [a for a in self.answers if a.problem.subtype == sub]
            if mine:
                out.append((sub, sum(a.correct for a in mine), len(mine)))
        return out

    @property
    def misses(self) -> list[Answer]:
        return [a for a in self.answers if not a.correct]

    def log_rows(self) -> list[dict[str, Any]]:
        return [{"level": a.problem.level, "family": PROB, "subtype": a.problem.subtype, "track": PROB_TRACK,
                 "outcome": a.outcome, "ms": a.ms} for a in self.answers]
