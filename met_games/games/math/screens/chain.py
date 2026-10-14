"""Chain: the run screen (CARRY, LINK with the input, CHAIN LOG, STEP CLOCK) and its report (tiles, the full chain
log, BROKE AT with the tip for that track)."""

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

from met_games.games.math.chain import PERCENT, TIMEOUT, ChainRun
from met_games.games.math.history import file_arcade
from met_games.games.math.ladder import TRACK_LABELS
from met_games.games.math.run import points
from met_games.bigtext import width
from met_games.games.math.screens.common import ClockScreen, big, crumb, secs, start_run
from met_games.games.math.screens.display import problem_rows, size_of
from met_games.games.math.screens.play import combo_bar
from met_games.games.math.tips import render
from met_games.pause import GameKeyBar, to_lobby
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar

LOG_N = 8
INPUT_W = 12
CLOCK_BAR = 20
BEST_LABELS = {"length": "longest chain", "points": "points"}


def tenths(ms: int) -> str:
    """7.3 — from whole milliseconds, rounded up to the tenth (0.0 only when it's over)."""
    t = -(-ms // 100)
    return f"{t // 10}.{t % 10}"


def link_line(done, show_carry: bool = True) -> Text:
    link = done.link
    out = Text()
    out.append(f"{link.carry} " if show_carry else "? ", style="bold")
    out.append(f"{link.op_text} = ")
    out.append(str(link.answer), style="bold")
    return out


class ChainScreen(ClockScreen):
    BINDINGS = [
        Binding("enter", "submit", "submit", priority=True),
        Binding("backspace", "backspace", "erase", priority=True),
        Binding("ctrl+e", "end_run", "end run", priority=True),
    ]

    DEFAULT_CSS = """
    ChainScreen #strip { height: 1; padding: 0 1; background: #1C232C; }
    ChainScreen #body { height: 1fr; }
    ChainScreen #left { width: 1fr; }
    ChainScreen #right { width: 40; }
    ChainScreen #carry, ChainScreen #step-clock { text-align: center; }
    ChainScreen #link { padding: 1 1; }
    """

    run: ChainRun

    def compose(self) -> ComposeResult:
        yield TopBar(crumb(self.run), f"SEED {self.run.seed}")
        yield Static(id="strip")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("CARRY", Static(id="carry"), id="carry-panel")
                yield TitledPanel("LINK", Static(id="link"), double=True, id="link-panel")
                yield TitledPanel("CHAIN LOG", Static(id="log"), id="log-panel")
            with Vertical(id="right"):
                yield TitledPanel("STEP CLOCK", Static(id="step-clock"))
                yield TitledPanel("THIS CHAIN", Static(id="ops"))
        yield GameKeyBar([("0–9", "type"), ("⌫", "erase"), ("⏎", "submit"), ("^E", "end run")])

    # ── view ────────────────────────────────────────────────────────────────

    def refresh_view(self) -> None:
        r = self.run
        self.query_one("#strip", Static).update(self.strip_text())
        if r.hidden:
            carry = big("?", f"bold {DIM}")
            carry.append("\nhidden — keep it in your head", style=DIM)
        else:
            carry = big(str(r.carry), f"bold {AMBER}")
            carry.append(f"\nstart {r.start}", style=DIM)
        self.query_one("#carry", Static).update(carry)
        self.query_one("#link", Static).update(self.link_text())
        self.query_one("#log", Static).update(self.log_text())
        left = r.time_left_ms
        clock = big(tenths(left), f"bold {RED if left <= 3_000 else AMBER}")
        filled = -(-left * CLOCK_BAR // r.rules.step_ms)
        clock.append("\n" + "█" * filled + "░" * (CLOCK_BAR - filled), style=RED if left <= 3_000 else AMBER)
        clock.append(f"\n{r.rules.step_ms // 1000}s per link", style=DIM)
        self.query_one("#step-clock", Static).update(clock)
        self.query_one("#ops", Static).update(self.ops_text())

    def strip_text(self) -> Text:
        r = self.run
        out = Text()
        out.append("LENGTH ", style=DIM)
        out.append(str(r.length), style=f"bold {GREEN}")
        out.append("   POINTS ", style=DIM)
        out.append(f"{r.points:,}", style=f"bold {AMBER}")
        out.append("   COMBO ", style=DIM)
        out.append(f"×{float(r.combo):.1f} ", style=f"bold {RED if r.combo >= 2 else AMBER}")
        out.append_text(combo_bar(r.combo))
        return out

    def link_text(self) -> Text:
        r = self.run
        link = r.link
        out = Text()
        out.append(f" link {r.length + 1} ", style=f"bold #000000 on {AMBER}")
        out.append(f"  {TRACK_LABELS[link.track]}", style=DIM)
        out.append(f"  +{points(link.base, r.length)}", style=f"bold {GREEN}")
        out.append("\n\n")
        room = self.query_one("#link", Static).content_size.width
        carry = "?" if r.hidden else str(link.carry)
        carry_style = f"bold {DIM}" if r.hidden else f"bold {AMBER}"
        rows = problem_rows(f"{carry} {link.op_text} =", self.problem_size, room)
        if rows is None:
            out.append(carry, style=carry_style)
            out.append(f" {link.op_text}", style="bold")
            out.append("  =\n\n")
        else:  # big: the carry's columns keep their colour (amber on EASY / MEDIUM)
            cut = width(carry, size_of(rows))
            for i, row in enumerate(rows):
                out.append(("\n" if i else "") + row[:cut], style=carry_style)
                out.append(row[cut:], style="bold")
            out.append("\n\n")
        self.answer_into(out, r.typed, room, INPUT_W)
        return out

    def log_text(self) -> Text:
        r = self.run
        if r.hidden:
            return Text("hidden on HARD", style=DIM)
        if not r.links:
            return Text("no links yet", style=DIM)
        out = Text()
        for i, d in enumerate(r.links[-LOG_N:][::-1]):
            if i:
                out.append("\n")
            out.append_text(link_line(d))
            out.append(f"   {secs(d.ms)}", style=DIM)
            out.append(f"   +{d.points}", style=f"bold {GREEN}")
        return out

    def ops_text(self) -> Text:
        rules = self.run.rules
        out = Text()
        out.append("carry ", style=DIM)
        out.append(f"1–{rules.max_carry:,}", style="bold")
        out.append("\n± ", style=DIM)
        out.append(f"1–{rules.add_max}", style="bold")
        if rules.mul_max:
            out.append("   × ", style=DIM)
            out.append(f"2–{rules.mul_max}", style="bold")
        if rules.div_max:
            out.append("   ÷ ", style=DIM)
            out.append(f"2–{rules.div_max}", style="bold")
        if rules.percents:
            out.append("\n% ", style=DIM)
            pcts = rules.percents
            out.append("any whole %" if len(pcts) > 10 else " ".join(str(p) for p in pcts), style="bold")
        out.append("\n\nwrong or out of time: the chain breaks", style=DIM)
        return out

    # ── input ───────────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        ch = event.character
        if ch and ch.isdigit():
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
        self.run.submit()
        if self.run.over:
            self.finish()
        else:
            self.refresh_view()

    def report_screen(self) -> Screen:
        return ChainReportScreen(self.run)


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True, overflow="ellipsis")
    return t


class ChainReportScreen(Screen):
    BINDINGS = [
        Binding("r", "again", "again"),
        Binding("l", "lobby", "lobby"),
        Binding("escape", "lobby", "lobby", show=False),
    ]

    DEFAULT_CSS = """
    ChainReportScreen #report-body { height: 1fr; padding: 0 1; }
    ChainReportScreen #tiles { height: auto; }
    ChainReportScreen .tile { width: 1fr; }
    ChainReportScreen .tile > Static { height: 7; }
    ChainReportScreen #lower { height: auto; }
    ChainReportScreen #log-col { width: 3fr; height: auto; }
    ChainReportScreen #broke-col { width: 2fr; height: auto; }
    """

    def __init__(self, run: ChainRun) -> None:
        super().__init__()
        self.run = run
        self.beaten, self.last = file_arcade(run)

    def compose(self) -> ComposeResult:
        r = self.run
        yield TopBar(f"{crumb(r)} ▸ REPORT", f"SEED {r.seed}")
        if r.ended_early:
            yield Static("■ ENDED EARLY · scored on the links you finished", classes="event-banner", id="ended-early")
        if self.beaten:
            what = " · ".join(BEST_LABELS[b] for b in self.beaten)
            yield Static(f"★ NEW BEST · {what}", classes="event-banner", id="new-best")
        with VerticalScroll(id="report-body"):
            with Horizontal(id="tiles"):
                yield TitledPanel("LENGTH", Static(self.length_tile()), classes="tile")
                yield TitledPanel("POINTS", Static(self.points_tile()), classes="tile")
                yield TitledPanel("AVG STEP TIME", Static(self.avg_tile()), classes="tile")
                yield TitledPanel("LAST 5 RUNS", Static(self.last_tile()), classes="tile")
            with Horizontal(id="lower"):
                with Vertical(id="log-col"):
                    yield TitledPanel("CHAIN LOG", Static(self.log_table(), id="chain-log"), double=True)
                with Vertical(id="broke-col"):
                    yield TitledPanel("BROKE AT", Static(self.broke_text(), id="broke-at"))
        yield KeyBar([("R", "again"), ("L", "lobby")])

    def length_tile(self) -> Text:
        out = big(str(self.run.length), f"bold {GREEN}")
        out.append(f"\nlinks · start {self.run.start}", style=DIM)
        return out

    def points_tile(self) -> Text:
        out = big(str(self.run.points), f"bold {AMBER}")
        out.append(f"\nbest combo ×{float(self.run.best_combo):.1f}", style=DIM)
        return out

    def avg_tile(self) -> Text:
        avg = self.run.avg_ms
        out = big(tenths(int(avg)) if avg is not None else "-", f"bold {TITLE}")
        out.append("\nseconds per link", style=DIM)
        return out

    def last_tile(self) -> Text:
        if not self.last:
            return Text("—", style=DIM)
        out = Text()
        for i, x in enumerate(reversed(self.last)):
            out.append(("\n" if i else "") + f"{x.get('date', '')[5:]:<6}", style=DIM)
            out.append(f"{x.get('length', 0)} long · {x.get('points', 0):,} pts", style=f"bold {AMBER}" if i == 0 else "")
        return out

    def log_table(self) -> Table | Text:
        r = self.run
        rows = r.links + ([r.broke] if r.broke else [])
        if not rows:
            return Text("no links answered", style=DIM)
        t = _table("#", "LINK", "ANSWER", "TIME", "PTS", right=("#", "ANSWER", "TIME", "PTS"))
        for i, d in enumerate(rows, 1):
            broke = d is r.broke
            t.add_row(str(i), d.link.text, (d.given or "—") if broke else str(d.link.answer), secs(d.ms),
                      "✗" if broke else f"+{d.points}", style=f"bold {RED}" if broke else None)
        return t

    def broke_text(self) -> Text:
        r = self.run
        d = r.broke
        if d is None:
            return Text("you ended the chain — nothing broke it", style=DIM)
        link = d.link
        out = Text()
        out.append(f"link {r.length + 1}: ", style=DIM)
        out.append(link.text, style="bold")
        out.append("\nyou    ", style=DIM)
        out.append("time ran out" if d.outcome == TIMEOUT else d.given, style=f"bold {RED}")
        out.append("\nright  ", style=DIM)
        out.append(str(link.answer), style=f"bold {GREEN}")
        problem = link.problem()
        title, rule, example = render(problem.tip_key, problem)
        out.append(f"\n\n{TRACK_LABELS[link.track]} · {title}", style=f"bold {AMBER}")
        out.append(f"\n{rule}")
        if example:
            out.append(f"\n{example}", style=f"bold {GREEN}")
        if link.kind == PERCENT:  # the tip covers p% of the carry; the link then adds or takes it off
            part = link.carry * link.operand // 100
            out.append(f"\nthen {link.carry} {link.op[0]} {part} = {link.answer}", style=f"bold {GREEN}")
        return out

    def action_again(self) -> None:
        start_run(self.app, self.run.config.replace(seed=None), switch=True)

    def action_lobby(self) -> None:
        to_lobby(self.app)
