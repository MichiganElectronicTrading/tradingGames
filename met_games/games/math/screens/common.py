"""Shared pieces of the Mental Math screens: the clock bridge, starting runs, and small renderers."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from rich.text import Text
from textual.app import App
from textual.screen import Screen

from met_games.games.math import daily
from met_games.games.math.config import CHAIN, DAILY, ESTIMATE, FLOW, MODE_LABELS, PROB_DRILL, MathConfig
from met_games.games.math.history import HISTORY_FILE, file_run
from met_games.games.math.run import new_run, new_seed
from met_games.pause import GameScreen
from met_games.widgets import big_lines


def crumb(run: Any) -> str:
    board = "" if run.board == "standard" else f" · {run.board.upper()}"
    return f"MATH ▸ {MODE_LABELS[run.mode]}{board}"


def clock_text(ms: int) -> str:
    s = -(-ms // 1000)  # whole seconds, rounded up: 0:00 only when it's over
    return f"{s // 60}:{s % 60:02d}"


def big(text: str, style: str) -> Text:
    out = Text()
    for i, line in enumerate(big_lines(text)):
        out.append(("\n" if i else "") + line, style=style)
    return out


def secs(ms: Fraction | int | None, places: int = 1) -> str:
    return "—" if ms is None else f"{float(ms) / 1000:.{places}f}s"


def run_seed(app: App, config: MathConfig | None = None) -> int:
    """The config's seed, else `--seed`, else a fresh one."""
    if config is not None and config.seed is not None:
        return config.seed
    override = getattr(app, "seed_override", None)
    return override if override is not None else new_seed()


def play_screen(run: Any) -> Screen:
    from met_games.games.math.run import OptiverRun
    from met_games.games.math.screens.play import OptiverScreen, RunScreen

    if run.mode == CHAIN:
        from met_games.games.math.screens.chain import ChainScreen

        return ChainScreen(run)
    if run.mode == ESTIMATE:
        from met_games.games.math.screens.estimate import EstimateScreen

        return EstimateScreen(run)
    if run.mode == FLOW:
        from met_games.games.math.screens.flow import FlowScreen

        return FlowScreen(run)
    if run.mode == PROB_DRILL:
        from met_games.games.math.screens.prob import ProbScreen

        return ProbScreen(run)
    return OptiverScreen(run) if isinstance(run, OptiverRun) else RunScreen(run)


def make_run(config: MathConfig, seed: int) -> Any:
    if config.mode == CHAIN:
        from met_games.games.math.chain import ChainRun

        return ChainRun(config, seed)
    if config.mode == ESTIMATE:
        from met_games.games.math.estimate import EstimateRun

        return EstimateRun(config, seed)
    if config.mode == FLOW:
        from met_games.games.math.flow import FlowRun

        return FlowRun(config, seed)
    if config.mode == PROB_DRILL:
        from met_games.games.math.probdrill import ProbRun

        return ProbRun(config, seed)
    return new_run(config, seed)


def start_run(app: App, config: MathConfig, *, switch: bool) -> None:
    run = make_run(config, run_seed(app, config))
    (app.switch_screen if switch else app.push_screen)(play_screen(run))


class ClockScreen(GameScreen):
    """Bridges real (or injected: `app.math_clock`) time to a run's millisecond clock. Paused, that clock stops —
    except in the daily, whose clock keeps running and whose "leave" ends the attempt with the score so far."""

    CLOCK_ATTR = "math_clock"

    def __init__(self, run: Any) -> None:
        super().__init__()
        self.run = run
        self.t0 = 0.0
        self.leaving = False

    def on_mount(self) -> None:
        self.t0 = self.clock()
        self.refresh_view()
        self.ticker = self.set_interval(0.1, self.sync)

    def sync(self) -> None:
        if self.leaving:
            return
        self.sync_to_now()
        if self.run.over:
            self.finish()
        else:
            self.refresh_view()

    def finish(self) -> None:
        if self.leaving:
            return
        self.leaving = True
        self.ticker.stop()
        self.run.end()
        self.front()
        self.app.switch_screen(self.report_screen())

    def report_screen(self) -> Screen:
        from met_games.games.math.screens.report import ReportScreen

        return ReportScreen(self.run)

    def action_end_run(self) -> None:
        self.sync()
        if not self.leaving:
            self.run.ended_early = True
            self.finish()

    # ── the pause menu ──────────────────────────────────────────────────────

    @property
    def is_daily(self) -> bool:
        return self.run.mode == DAILY

    def clock_runs_while_paused(self) -> bool:
        return self.is_daily

    def menu_note(self) -> str:
        return "daily clock keeps running" if self.is_daily else ""

    def leave_prompt(self) -> str:
        if self.is_daily:
            return "Leave the daily? It ends now with your score so far and uses today's attempt. [Y/N]"
        return super().leave_prompt()

    def abandon_record(self) -> tuple[str, dict[str, Any]]:
        r = self.run
        return HISTORY_FILE, {"mode": r.mode, "difficulty": r.board, "seed": r.seed}

    def leave_game(self) -> None:
        if not self.is_daily:
            super().leave_game()
            return
        self.action_end_run()  # the attempt counts: the report shows ENDED EARLY

    def quit_game(self) -> None:
        if self.is_daily and not self.leaving:
            self.leaving = True
            self.ticker.stop()
            self.sync_to_now()
            self.run.ended_early = True
            self.run.end()
            file_run(self.run)
            daily.save_result(self.run.day, self.run)
            self.app.exit()
            return
        super().quit_game()

    def sync_to_now(self) -> None:
        self.run.advance_to(int((self.clock() - self.t0) * 1000))

    def refresh_view(self) -> None:
        """Redraw from the run (subclasses)."""
