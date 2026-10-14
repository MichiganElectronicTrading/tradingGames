"""The post-run report (tiles, WEAKNESS REPORT, SLOWEST 3, SHORTCUT) and the all-tips screen."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math import daily
from met_games.games.math.config import DAILY, DRILL, FLOW, OPTIVER, ZETAMAC
from met_games.games.math.history import drill_pool, file_run
from met_games.games.math.problems import SUBTYPE_LABELS
from met_games.games.math.run import SKIPPED, WRONG, OptiverRun, new_drill, new_focus_drill
from met_games.games.math.screens.common import big, crumb, play_screen, run_seed, secs, start_run
from met_games.games.math.tips import SUBTYPE_TIPS, TIPS, render
from met_games.pause import to_lobby
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar

WEAK_STYLE = "bold #FFFFFF on #7A1F1F"
BEST_LABELS = {"correct": "correct", "points": "points", "raw": "raw score", "net": "net"}


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True, overflow="ellipsis")
    return t


class ReportScreen(Screen):
    BINDINGS = [
        Binding("d", "drill", "drill"),
        Binding("t", "tips", "all tips"),
        Binding("r", "again", "run again"),
        Binding("c", "card", "copy score card"),
        Binding("l", "lobby", "lobby"),
        Binding("escape", "lobby", "lobby", show=False),
    ]

    DEFAULT_CSS = """
    ReportScreen #report-body { height: 1fr; padding: 0 1; }
    ReportScreen #tiles { height: auto; }
    ReportScreen .tile { width: 1fr; }
    ReportScreen .tile > Static { height: 7; }
    ReportScreen #lower { height: auto; }
    ReportScreen #lower-left { width: 3fr; height: auto; }
    ReportScreen #lower-right { width: 2fr; height: auto; }
    """

    def __init__(self, run) -> None:
        super().__init__()
        self.run = run
        self.report, self.beaten = file_run(run)
        if run.mode == DAILY and run.day is not None:
            daily.save_result(run.day, run)

    def compose(self) -> ComposeResult:
        r, rep = self.run, self.report
        yield TopBar(f"{crumb(r)} ▸ REPORT", f"SEED {r.seed}" if r.mode != DAILY else f"DAILY #{daily.number(r.day)}")
        if r.ended_early:
            yield Static("■ ENDED EARLY · scored on what you answered before you left", classes="event-banner",
                         id="ended-early")
        if self.beaten:
            what = " · ".join(BEST_LABELS[b] for b in self.beaten)
            yield Static(f"★ NEW BEST · {what}", classes="event-banner", id="new-best")
        with VerticalScroll(id="report-body"):
            with Horizontal(id="tiles"):
                yield TitledPanel("CORRECT", Static(self.correct_tile()), classes="tile")
                yield TitledPanel(self.score_title(), Static(self.score_tile()), classes="tile")
                yield TitledPanel("AVG TIME", Static(self.avg_tile()), classes="tile")
                yield TitledPanel("LAST 5 RUNS", Static(self.last_runs_tile()), classes="tile")
            if r.mode == FLOW:
                yield TitledPanel(f"ALL {len(r.questions)}", Static(self.flow_table(), id="flow-rows"), double=True)
            yield TitledPanel("WEAKNESS REPORT", Static(self.weakness_table()), double=True)
            with Horizontal(id="lower"):
                with Vertical(id="lower-left"):
                    yield TitledPanel("SLOWEST 3", Static(self.slowest_text()))
                with Vertical(id="lower-right"):
                    yield TitledPanel("SHORTCUT", Static(self.shortcut_text()), id="shortcut")
        yield KeyBar([("D", "drill"), ("T", "all tips"), ("R", "run again"), ("C", "copy score card"), ("L", "lobby")])

    # ── tiles ───────────────────────────────────────────────────────────────

    def correct_tile(self) -> Text:
        r = self.run
        out = big(str(r.correct), f"bold {GREEN}")
        out.append(f"\n{r.skipped} skipped", style=DIM)
        if isinstance(r, OptiverRun) or r.mode == FLOW:
            out.append(f" · {r.wrong} wrong", style=RED if r.wrong else DIM)
        return out

    def score_title(self) -> str:
        return {ZETAMAC: "RAW SCORE", OPTIVER: "NET", FLOW: "SCORE"}.get(self.run.mode, "POINTS")

    def score_tile(self) -> Text:
        r = self.run
        if r.mode == ZETAMAC:
            out = big(str(r.correct), f"bold {AMBER}")
            out.append("\nraw score · no points", style=DIM)
            return out
        if r.mode == FLOW:
            out = big(str(r.correct), f"bold {AMBER}")
            out.append(f"\nof {len(r.questions)} · unofficial practice format", style=DIM)
            return out
        if r.mode == OPTIVER:
            out = big(f"{r.net}", f"bold {AMBER}")
            out.append(f"\n+{r.correct} −{r.wrong} · unofficial practice", style=DIM)
            return out
        out = big(str(r.points), f"bold {AMBER}")
        out.append(f"\nbest combo ×{float(r.best_combo):.1f}", style=DIM)
        return out

    def avg_tile(self) -> Text:
        avg = self.report.avg_ms
        out = big(f"{float(avg) / 1000:.1f}" if avg is not None else "-", f"bold {TITLE}")
        out.append("\nseconds per correct answer", style=DIM)
        return out

    def last_runs_tile(self) -> Text:
        runs = self.report.last_runs
        if not runs:
            return Text("—", style=DIM)
        out = Text()
        for i, x in enumerate(reversed(runs)):
            out.append(("\n" if i else "") + f"{x.get('date', '')[5:]:<6}", style=DIM)
            if x["mode"] == OPTIVER:
                score = f"net {x['correct'] - x.get('wrong', 0):+d}"
            elif x["mode"] == ZETAMAC:
                score = f"{x['correct']} raw"
            elif x["mode"] == FLOW:
                score = f"{x['correct']} ✓ of 60"
            else:
                score = f"{x['correct']} ✓ · {x.get('points', 0):,} pts"
            out.append(score, style=f"bold {AMBER}" if i == 0 else "")
        return out

    # ── weakness, slowest, shortcut ─────────────────────────────────────────

    def weakness_table(self) -> Table | Text:
        rows = self.report.rows
        if not rows:
            return Text("no problems answered", style=DIM)
        weak = {r.subtype for r in self.report.weak}
        t = _table("TYPE", "SEEN", "RIGHT", "AVG", "USUAL", "VS USUAL", right=("SEEN", "RIGHT", "AVG", "USUAL"))
        for r in rows:
            t.add_row(r.label, str(r.seen), f"{100 * r.right // r.seen}%", secs(r.avg_ms), secs(r.usual_ms), r.vs,
                      style=WEAK_STYLE if r.subtype in weak else None)
        return t

    def flow_table(self) -> Table:
        """Every question: what you typed, the answer and your time; wrong answers highlighted."""
        r = self.run
        t = _table("#", "QUESTION", "YOU", "ANSWER", "TIME", right=("#", "YOU", "ANSWER", "TIME"))
        for i, p in enumerate(r.questions):
            a = r.attempts[i] if i < len(r.attempts) else None
            if a is None:
                t.add_row(str(i + 1), p.text, "—", p.answer_text, "—", style=DIM)
                continue
            you = "skipped" if a.outcome == SKIPPED else a.given
            t.add_row(str(i + 1), p.text, you, p.answer_text, secs(a.ms),
                      style=WEAK_STYLE if a.outcome == WRONG else (DIM if a.outcome == SKIPPED else None))
        return t

    def slowest_text(self) -> Text:
        out = Text()
        for i, a in enumerate(self.report.slowest):
            out.append(("\n" if i else "") + f"{secs(a.ms):>6}  ", style=f"bold {AMBER}")
            out.append(f"{a.problem.text} = {a.problem.answer_text}", style="bold")
            if a.outcome == SKIPPED:
                out.append("  skipped", style=RED)
            elif a.outcome == WRONG:
                out.append(f"  you: {a.given}", style=RED)
        return out or Text("—", style=DIM)

    def shortcut_text(self) -> Text:
        if self.report.shortcut is None:
            return Text("—", style=DIM)
        title, rule, example = self.report.shortcut
        out = Text(title, style=f"bold {AMBER}")
        out.append(f"\n{rule}")
        if example:
            out.append(f"\n{example}", style=f"bold {GREEN}")
        return out

    # ── keys ────────────────────────────────────────────────────────────────

    def action_drill(self) -> None:
        pool = drill_pool(self.report.rows, self.run.attempts)
        if not pool:
            self.app.bell()
            self.notify("nothing to drill yet", severity="warning")
            return
        run = new_drill(run_seed(self.app), pool, self.run.board)
        self.app.switch_screen(play_screen(run))

    def action_tips(self) -> None:
        self.app.push_screen(TipsScreen())

    def action_again(self) -> None:
        r = self.run
        if r.mode == DAILY:
            self.app.bell()
            self.notify("one daily attempt per day — come back tomorrow", severity="warning")
            return
        if getattr(r, "focus", None):
            self.app.switch_screen(play_screen(new_focus_drill(run_seed(self.app), r.focus)))
            return
        if r.mode == DRILL:
            pool = sorted({(a.problem.family, a.problem.subtype, a.problem.level) for a in r.attempts})
            if pool:
                self.app.switch_screen(play_screen(new_drill(run_seed(self.app), pool, r.board)))
            return
        if r.mode == OPTIVER:
            self.app.switch_screen(play_screen(OptiverRun(run_seed(self.app))))
            return
        start_run(self.app, r.config.replace(seed=None), switch=True)

    def action_card(self) -> None:
        r = self.run
        card = daily.daily_card(r.day, daily.result_of(r)) if r.mode == DAILY else daily.run_card(r)
        if daily.copy(card):
            self.notify("score card copied")
        else:
            self.notify(card, title="pbcopy not found — your card:", timeout=20)

    def action_lobby(self) -> None:
        to_lobby(self.app)


class TipsScreen(Screen):
    """T on the report: every shortcut, grouped by problem type."""

    BINDINGS = [Binding("escape", "app.pop_screen", "back"), Binding("t", "app.pop_screen", "back", show=False)]

    DEFAULT_CSS = """
    TipsScreen #tips-scroll { height: 1fr; margin: 0 1; border: double #3FA7B5; border-title-color: #5FD4E0;
                              border-title-style: bold; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield TopBar("MATH ▸ SHORTCUTS")
        out = Text()
        for i, (sub, keys) in enumerate(SUBTYPE_TIPS.items()):
            out.append(("\n\n" if i else "") + SUBTYPE_LABELS[sub].upper(), style=f"bold {TITLE}")
            for key in keys:
                title, rule, _ = render(key)
                out.append(f"\n{title:<20}", style=f"bold {AMBER}")
                out.append(rule)
        scroll = VerticalScroll(Static(out), id="tips-scroll")
        scroll.border_title = f"ALL TIPS · {len(TIPS)}"
        yield scroll
        yield KeyBar([("↑↓", "scroll"), ("Esc", "back")])

