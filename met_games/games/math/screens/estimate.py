"""Estimate: the run screen (band counts, QUESTION with the input, LAST 4, CLOCK, SCORING) and its report (the full
15-row table and the band counts)."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math.estimate import (
    FULL,
    HALF,
    KIND_LABELS,
    MISS,
    QUARTER,
    QUESTION_MS,
    EstimateRun,
    percent_text,
    points_text,
    speed_text,
    two_dp,
)
from met_games.games.math.history import file_arcade
from met_games.games.math.screens.chain import tenths
from met_games.games.math.screens.common import ClockScreen, big, crumb, secs, start_run
from met_games.pause import GameKeyBar, to_lobby
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar

LAST_N = 4
INPUT_W = 16
CLOCK_BAR = 20
BAND_STYLE = {FULL: f"bold {GREEN}", HALF: f"bold {AMBER}", QUARTER: f"bold {TITLE}", MISS: f"bold {RED}"}


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True, overflow="ellipsis")
    return t


def rows_table(rows) -> Table:
    """problem · exact (2 dp) · you · off % · time · × · pts."""
    t = _table("PROBLEM", "EXACT", "YOU", "OFF", "TIME", "×", "PTS", right=("EXACT", "YOU", "OFF", "TIME", "PTS"))
    for r in rows:
        timed_out = r.guess is None
        t.add_row(r.question.text, two_dp(r.question.exact), "—" if timed_out else r.typed,
                  "timeout" if timed_out else percent_text(r.off), secs(r.ms), "" if timed_out else speed_text(r.speed),
                  Text(points_text(r.points), style=BAND_STYLE[r.band]))
    return t


def band_counts(run: EstimateRun) -> Text:
    out = Text()
    for i, (name, label) in enumerate(((FULL, "FULL"), (HALF, "HALF"), (QUARTER, "QUARTER"), (MISS, "MISS"))):
        out.append(("   " if i else "") + f"{label} ", style=DIM)
        out.append(str(run.count(name)), style=BAND_STYLE[name])
    return out


class EstimateScreen(ClockScreen):
    BINDINGS = [
        Binding("enter", "submit", "submit", priority=True),
        Binding("backspace", "backspace", "erase", priority=True),
        Binding("ctrl+e", "end_run", "end run", priority=True),
    ]

    DEFAULT_CSS = """
    EstimateScreen #strip { height: 1; padding: 0 1; background: #1C232C; }
    EstimateScreen #body { height: 1fr; }
    EstimateScreen #left { width: 1fr; }
    EstimateScreen #right { width: 40; }
    EstimateScreen #question { padding: 1 1; }
    EstimateScreen #clock { text-align: center; }
    """

    run: EstimateRun

    def compose(self) -> ComposeResult:
        yield TopBar(crumb(self.run), f"SEED {self.run.seed}")
        yield Static(id="strip")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("QUESTION", Static(id="question"), double=True)
                yield TitledPanel("LAST 4", Static(id="last"))
            with Vertical(id="right"):
                yield TitledPanel("CLOCK", Static(id="clock"))
                yield TitledPanel("SCORING", Static(self.scoring_text()))
        yield GameKeyBar([("0–9 . ,", "type"), ("⌫", "erase"), ("⏎", "submit"), ("^E", "end run")])

    def refresh_view(self) -> None:
        r = self.run
        strip = Text()
        strip.append("POINTS ", style=DIM)
        strip.append(points_text(r.points), style=f"bold {AMBER}")
        strip.append("   ")
        strip.append_text(band_counts(r))
        strip.append(f"   Q {min(len(r.rows) + 1, len(r.questions))}/{len(r.questions)}", style=DIM)
        self.query_one("#strip", Static).update(strip)
        self.query_one("#question", Static).update(self.question_text())
        rows = r.rows[-LAST_N:][::-1]
        self.query_one("#last", Static).update(rows_table(rows) if rows else Text("no answers yet", style=DIM))
        left = r.time_left_ms
        clock = big(tenths(left), f"bold {RED if left <= 4_000 else AMBER}")
        filled = -(-left * CLOCK_BAR // QUESTION_MS)
        clock.append("\n" + "█" * filled + "░" * (CLOCK_BAR - filled), style=RED if left <= 4_000 else AMBER)
        self.query_one("#clock", Static).update(clock)

    def question_text(self) -> Text:
        r = self.run
        q = r.question
        out = Text()
        if q is None:
            return out
        out.append(f" {KIND_LABELS[q.kind]} ", style=f"bold #000000 on {AMBER}")
        out.append("  ≈ within 1% for full points", style=DIM)
        out.append("\n\n")
        room = self.query_one("#question", Static).content_size.width
        self.problem_into(out, q.text, "  ≈\n\n", room, big_suffix="")  # √ and "% of" stay NORMAL
        self.answer_into(out, r.typed, room, INPUT_W)
        return out

    def scoring_text(self) -> Text:
        out = Text()
        for limit, pts in (("≤ 1%", "100 FULL"), ("≤ 5%", " 50 HALF"), ("≤ 10%", " 25 QUARTER"), ("over", "  0 MISS")):
            out.append(f"{limit:<6}", style=DIM)
            out.append(f"{pts}\n", style="bold")
        out.append("\n≤ 4s ×2 · ≤ 8s ×1.5 · timeout 0", style=DIM)
        return out

    def on_key(self, event: events.Key) -> None:
        ch = event.character
        if ch and (ch.isdigit() or ch in ".,"):
            event.stop()
            event.prevent_default()
            if not self.leaving:
                self.run.type(ch)
                self.refresh_view()

    def action_backspace(self) -> None:
        self.run.backspace()
        self.refresh_view()

    def action_submit(self) -> None:
        if self.leaving:
            return
        self.sync()
        if self.leaving:
            return
        if self.run.submit() is None and self.run.typed:
            self.app.bell()  # not a number
        if self.run.over:
            self.finish()
        else:
            self.refresh_view()

    def report_screen(self) -> Screen:
        return EstimateReportScreen(self.run)


class EstimateReportScreen(Screen):
    BINDINGS = [
        Binding("r", "again", "again"),
        Binding("l", "lobby", "lobby"),
        Binding("escape", "lobby", "lobby", show=False),
    ]

    DEFAULT_CSS = """
    EstimateReportScreen #report-body { height: 1fr; padding: 0 1; }
    EstimateReportScreen #tiles { height: auto; }
    EstimateReportScreen .tile { width: 1fr; }
    EstimateReportScreen .tile > Static { height: 7; }
    """

    def __init__(self, run: EstimateRun) -> None:
        super().__init__()
        self.run = run
        self.beaten, self.last = file_arcade(run)

    def compose(self) -> ComposeResult:
        r = self.run
        yield TopBar(f"{crumb(r)} ▸ REPORT", f"SEED {r.seed}")
        if r.ended_early:
            yield Static("■ ENDED EARLY · scored on what you answered", classes="event-banner", id="ended-early")
        if self.beaten:
            yield Static("★ NEW BEST · points", classes="event-banner", id="new-best")
        with VerticalScroll(id="report-body"):
            with Horizontal(id="tiles"):
                yield TitledPanel("POINTS", Static(self.points_tile()), classes="tile")
                yield TitledPanel("BANDS", Static(self.bands_tile(), id="bands"), classes="tile")
                yield TitledPanel("LAST 5 RUNS", Static(self.last_tile()), classes="tile")
            yield TitledPanel(f"ALL {len(r.rows)}", Static(rows_table(r.rows) if r.rows else
                                                            Text("no answers", style=DIM), id="all-rows"),
                              double=True)
        yield KeyBar([("R", "again"), ("L", "lobby")])

    def points_tile(self) -> Text:
        out = big(points_text(self.run.points).replace(",", ""), f"bold {AMBER}")
        out.append(f"\n{len(self.run.rows)} answered · no combo", style=DIM)
        return out

    def bands_tile(self) -> Text:
        r = self.run
        out = Text()
        for i, (name, label) in enumerate(((FULL, "FULL ≤1%"), (HALF, "HALF ≤5%"), (QUARTER, "QUARTER ≤10%"),
                                           (MISS, "MISS"))):
            out.append(("\n" if i else "") + f"{label:<14}", style=DIM)
            out.append(str(r.count(name)), style=BAND_STYLE[name])
        out.append(f"\n{'timeouts':<14}", style=DIM)
        out.append(str(r.skipped), style="bold")
        return out

    def last_tile(self) -> Text:
        if not self.last:
            return Text("—", style=DIM)
        out = Text()
        for i, x in enumerate(reversed(self.last)):
            out.append(("\n" if i else "") + f"{x.get('date', '')[5:]:<6}", style=DIM)
            out.append(f"{x.get('points', 0):,} pts · {x.get('full', 0)} full", style=f"bold {AMBER}" if i == 0 else "")
        return out

    def action_again(self) -> None:
        start_run(self.app, self.run.config.replace(seed=None), switch=True)

    def action_lobby(self) -> None:
        to_lobby(self.app)
