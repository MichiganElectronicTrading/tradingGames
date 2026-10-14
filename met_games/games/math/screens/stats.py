"""MY STATS: ←→ picks the mode, ↑↓ the difficulty. LAST 20 RUNS (sparkline, first → median → latest), MEDIAN TIME
PER FAMILY (first 10 vs last 10 runs), ADAPTIVE LEVELS with 7-day arrows, BESTS, and FOCUS NEXT (F drills it)."""

from __future__ import annotations

from datetime import date

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math import daily
from met_games.games.math.adaptive import stored_levels, week_ago
from met_games.games.math.config import MODE_LABELS
from met_games.games.math.history import load_bests, load_history, load_runs
from met_games.games.math.ladder import ALL_TRACKS, LEVEL_MAX, TRACK_LABELS
from met_games.games.math.problems import FAMILIES
from met_games.games.math.progress import (
    PRIMARY,
    PRIMARY_LABELS,
    SPLIT_MIN,
    STATS_DIFFICULTIES,
    STATS_MODES,
    best_rows,
    best_value,
    exact,
    family_split,
    focus_next,
    header,
    level_rows,
    number,
    recent,
    run_order,
    sparkline,
    trend,
)
from met_games.games.math.run import new_focus_drill
from met_games.games.math.screens.common import play_screen, run_seed, secs
from met_games.games.math.ui import FAMILY_NAMES
from met_games.widgets import AMBER, DIM, GREEN, RED, SELECTED, TITLE, KeyBar, TitledPanel, TopBar


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True, overflow="ellipsis")
    return t


class StatsScreen(Screen):
    BINDINGS = [
        Binding("left", "mode(-1)", "mode", priority=True),
        Binding("right", "mode(1)", "mode", priority=True),
        Binding("up", "difficulty(-1)", "difficulty", priority=True),
        Binding("down", "difficulty(1)", "difficulty", priority=True),
        Binding("f", "focus", "focus drill"),
        Binding("escape", "app.pop_screen", "back"),
        Binding("l", "app.pop_screen", "lobby", show=False),
    ]

    DEFAULT_CSS = """
    StatsScreen #stats-body { height: 1fr; padding: 0 1; }
    StatsScreen #tabs { height: 2; padding: 0 1; }
    StatsScreen .stats-row { height: auto; }
    StatsScreen .stats-row > TitledPanel { width: 1fr; }
    """

    def __init__(self, today: date | None = None) -> None:
        super().__init__()
        self.today = today or date.today()
        self.mode_i = 0
        # MEDIUM first
        self.diff_i: dict[str, int] = {m: min(1, len(STATS_DIFFICULTIES[m]) - 1) for m in STATS_MODES}
        self.focus: tuple[str, str] | None = None

    def compose(self) -> ComposeResult:
        yield TopBar("MATH ▸ MY STATS", "", None, id="stats-top")
        yield Static(id="tabs")
        with VerticalScroll(id="stats-body"):
            with Horizontal(classes="stats-row"):
                yield TitledPanel("LAST 20 RUNS", Static(id="spark"), double=True, id="spark-panel")
                yield TitledPanel("ADAPTIVE LEVELS · 7 DAYS", Static(id="levels"), id="levels-panel")
            with Horizontal(classes="stats-row"):
                yield TitledPanel("MEDIAN TIME PER FAMILY", Static(id="medians"), id="medians-panel")
                yield TitledPanel("BESTS", Static(id="bests"), id="bests-panel")
            yield TitledPanel("FOCUS NEXT", Static(id="focus"), id="focus-panel")
        yield KeyBar([("←→", "mode"), ("↑↓", "difficulty"), ("F", "focus drill"), ("Esc", "back")])

    def on_mount(self) -> None:
        self.load()

    def on_screen_resume(self) -> None:
        self.load()

    # ── data ────────────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return STATS_MODES[self.mode_i]

    @property
    def difficulty(self) -> str:
        return STATS_DIFFICULTIES[self.mode][self.diff_i[self.mode]]

    def load(self) -> None:
        self.runs = load_runs()
        self.history = load_history()
        self.levels = stored_levels()
        self.week = week_ago(self.today)
        self.focus = focus_next(self.levels, self.week, self.history)
        total, first = header(self.runs)
        top = f"{total} run{'s' if total != 1 else ''}"
        top += f" · since {first}" if first else ""
        top += f" · daily streak {daily.streak(daily.today())}"
        self.query_one("#stats-top", TopBar).set(round_text=top)
        self.query_one("#levels", Static).update(self.levels_text())
        self.query_one("#medians", Static).update(self.medians_table())
        self.query_one("#bests", Static).update(self.bests_table())
        self.query_one("#focus", Static).update(self.focus_text())
        self.refresh_board()

    def refresh_board(self) -> None:
        self.query_one("#tabs", Static).update(self.tabs_text())
        self.query_one("#spark-panel").border_title = f"LAST 20 RUNS · {MODE_LABELS[self.mode]} · " \
                                                      f"{self.difficulty.upper()}"
        self.query_one("#spark", Static).update(self.spark_text())

    # ── panels ──────────────────────────────────────────────────────────────

    def tabs_text(self) -> Text:
        out = Text()
        for m in STATS_MODES:
            out.append(f" {MODE_LABELS[m]} ", style=SELECTED if m == self.mode else "bold")
            out.append(" ")
        out.append("\n")
        for d in STATS_DIFFICULTIES[self.mode]:
            out.append(f" {d.upper()} ", style=f"bold {AMBER} reverse" if d == self.difficulty else DIM)
            out.append(" ")
        return out

    def spark_text(self) -> Text:
        values = recent(self.runs, self.mode, self.difficulty)
        label = PRIMARY_LABELS[PRIMARY[self.mode]]
        if not values:
            return Text(f"no {MODE_LABELS[self.mode]} runs on {self.difficulty.upper()} yet", style=DIM)
        line = sparkline(values)
        out = Text()
        out.append("".join(ch * 2 for ch in line), style=f"bold {AMBER}")
        first, med, latest = trend(values)
        out.append(f"\n\n{label}: ", style=DIM)
        out.append(number(first), style="bold")
        out.append(" → ", style=DIM)
        out.append(number(med), style="bold")
        out.append(" → ", style=DIM)
        out.append(number(latest), style=f"bold {GREEN if latest >= med else RED}")
        out.append(f"\nfirst → median → latest · {len(values)} run{'s' if len(values) != 1 else ''}", style=DIM)
        return out

    def levels_text(self) -> Text:
        if self.levels is None:
            return Text("no adaptive runs yet — pick ADAPTIVE for Sprint, Survival or the Probability drill", style=DIM)
        out = Text()
        for i, (t, lv, arrow) in enumerate(level_rows(self.levels, self.week, ALL_TRACKS)):
            out.append(("\n" if i else "") + f"{TRACK_LABELS[t]:<5}", style="bold")
            if lv is None:
                out.append("not played yet", style=DIM)
                continue
            out.append("█" * lv + "░" * (LEVEL_MAX - lv), style=AMBER)
            out.append(f" L{lv:<2} ", style="bold")
            out.append(arrow, style=GREEN if arrow == "▲" else RED if arrow == "▼" else DIM)
        return out

    def medians_table(self) -> Table:
        split = family_split(self.history)
        t = _table("FAMILY", "FIRST 10", "LAST 10", right=("FIRST 10", "LAST 10"))
        for f in FAMILIES:
            first, last = split[f] if split else (None, None)
            style = None
            if first is not None and last is not None and last != first:
                style = GREEN if last < first else RED
            t.add_row(FAMILY_NAMES[f], secs(first), Text(secs(last), style=style or ""))
        if split is None:
            t.caption = f"— until {SPLIT_MIN} runs: you have {len(run_order(self.history))}"
            t.caption_style = DIM
        return t

    def bests_table(self) -> Table | Text:
        rows = best_rows(load_bests())
        t = _table("MODE", "AT", "BEST", "DATE")
        for mode, diff, entry in rows:
            best = best_value(mode, entry)
            if best is None:
                t.add_row(MODE_LABELS[mode], "—", "—", "—", style=DIM)
                continue
            field, value, day = best
            t.add_row(MODE_LABELS[mode], diff.upper(), f"{number(exact(value))} {PRIMARY_LABELS.get(field, field)}",
                      day or "—")
        return t

    def focus_text(self) -> Text:
        if self.focus is None:
            return Text("play a few runs — then this names the skill to work on", style=DIM)
        track, why = self.focus
        out = Text()
        out.append(f"{TRACK_LABELS[track]} ", style=f"bold {AMBER}")
        level = (self.levels or {}).get(track)
        if level is not None:
            out.append(f"L{level}  ", style="bold")
        out.append(why, style=DIM)
        out.append("\nF: a 2:00 adaptive Sprint on this track only — logged, never a best", style=DIM)
        return out

    # ── keys ────────────────────────────────────────────────────────────────

    def action_mode(self, delta: int) -> None:
        self.mode_i = (self.mode_i + delta) % len(STATS_MODES)
        self.refresh_board()

    def action_difficulty(self, delta: int) -> None:
        n = len(STATS_DIFFICULTIES[self.mode])
        self.diff_i[self.mode] = max(0, min(n - 1, self.diff_i[self.mode] + delta))
        self.refresh_board()

    def action_focus(self) -> None:
        if self.focus is None:
            self.app.bell()
            self.notify("nothing to focus on yet", severity="warning")
            return
        run = new_focus_drill(run_seed(self.app), self.focus[0])
        self.app.push_screen(play_screen(run))

