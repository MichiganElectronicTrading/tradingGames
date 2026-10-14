"""Flow-style 60 in 6 (an unofficial practice format): 60 typed questions in 6:00, core arithmetic and decimals &
fractions at MEDIUM–HARD. Enter submits (nothing locks by itself), an empty Enter skips, a wrong answer still moves
on, there is no going back and no right / wrong until the end. Score: the number correct. Pure Python, no Textual.
"""

from __future__ import annotations

import random
from fractions import Fraction

from met_games.games.math.config import FLOW, STANDARD, MathConfig
from met_games.games.math.problems import ALLOWED, CORE, DECFRAC, HARD, MEDIUM, Problem, accepts, make
from met_games.games.math.run import CORRECT, SKIPPED, WRONG, Attempt

QUESTIONS = 60
FLOW_MS = 360_000
FLOW_FAMILIES = (CORE, DECFRAC)
FLOW_LEVELS = (MEDIUM, HARD)
MAX_TYPED = 12


def flow_problems(seed: int | str) -> list[Problem]:
    """60 problems from the seed: core and decimals & fractions alternate out of shuffled bags, each at MEDIUM or
    HARD at random."""
    rng = random.Random(seed)
    out: list[Problem] = []
    bag: list[str] = []
    while len(out) < QUESTIONS:
        if not bag:
            bag = list(FLOW_FAMILIES)
            rng.shuffle(bag)
        out.append(make(rng, bag.pop(), rng.choice(FLOW_LEVELS)))
    return out


class FlowRun:
    def __init__(self, config: MathConfig, seed: int | str, problems: list[Problem] | None = None) -> None:
        config.validate()
        self.mode, self.board, self.seed, self.config = FLOW, STANDARD, seed, config
        self.questions = problems if problems is not None else flow_problems(seed)
        self.scored = False
        self.ladder = None
        self.day = None
        self.focus = None
        self.ended_early = False
        self.attempts: list[Attempt] = []
        self.duration_ms = FLOW_MS
        self.now = 0
        self.shown_at = 0
        self.typed = ""
        self.over = False
        self.best_combo = Fraction(1)

    @property
    def problem(self) -> Problem | None:
        i = len(self.attempts)
        return self.questions[i] if i < len(self.questions) else None

    @property
    def time_left_ms(self) -> int:
        return max(0, FLOW_MS - self.now)

    def advance_to(self, ms: int) -> None:
        if self.over or ms <= self.now:
            return
        self.now = ms
        if self.time_left_ms == 0:
            self.end()

    def end(self) -> None:
        self.over = True

    def type(self, ch: str) -> None:
        if not self.over and ch in ALLOWED and len(self.typed) < MAX_TYPED:
            self.typed += ch

    def backspace(self) -> None:
        if not self.over:
            self.typed = self.typed[:-1]

    def submit(self) -> Attempt | None:
        """Enter: an empty answer skips; anything else is marked (right or wrong, it isn't shown) and moves on."""
        if self.over:
            return None
        p = self.problem
        if not self.typed:
            outcome = SKIPPED
        else:
            outcome = CORRECT if accepts(p, self.typed) else WRONG
        attempt = Attempt(p, outcome, self.now - self.shown_at, 0, 0, self.typed)
        self.attempts.append(attempt)
        self.typed, self.shown_at = "", self.now
        if len(self.attempts) >= len(self.questions):
            self.end()
        return attempt

    # ── score ───────────────────────────────────────────────────────────────

    @property
    def answered(self) -> int:
        return len(self.attempts)

    @property
    def correct(self) -> int:
        return sum(a.outcome == CORRECT for a in self.attempts)

    @property
    def wrong(self) -> int:
        return sum(a.outcome == WRONG for a in self.attempts)

    @property
    def skipped(self) -> int:
        return sum(a.outcome == SKIPPED for a in self.attempts)

    @property
    def points(self) -> int:
        return 0

    def pace(self) -> tuple[Fraction | None, Fraction | None]:
        """(your seconds per question so far, the seconds per question that finishes the rest in time)."""
        avg = Fraction(self.now, 1000 * self.answered) if self.answered else None
        left = len(self.questions) - self.answered
        need = Fraction(self.time_left_ms, 1000 * left) if left else None
        return avg, need

    def on_pace(self) -> bool:
        """At or under the needed pace (no answers yet: on pace)."""
        avg, need = self.pace()
        return avg is None or need is None or avg <= need
