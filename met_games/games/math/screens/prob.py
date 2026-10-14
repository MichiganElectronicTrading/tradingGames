"""The Probability drill: the strip (answered, ✓, ✗, best), QUESTION with the input, WHY (the last answer's ✓ / ✗,
its explanation and any known mistake), CLOCK and SO FAR; and its report (score, accuracy per subtype, every miss
with its explanation)."""

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

from met_games.games.math.history import best_key, file_arcade, load_bests
from met_games.games.math.ladder import PROB_TRACK
from met_games.games.math.prob import COUNT, SUBTYPE_LABELS
from met_games.games.math.probdrill import KEYS, Answer, ProbRun
from met_games.games.math.screens.common import ClockScreen, big, clock_text, crumb, secs, start_run
from met_games.pause import GameKeyBar, to_lobby
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar

TAGLINE = "dice · cards · coins · expected value · counting"
INPUT_W = 18
SO_FAR_N = 10


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True, overflow="ellipsis")
    return t


def why_text(a: Answer) -> Text:
    """✓, or ✗ with the right answer; then the explanation, and the known mistake if one matched."""
    out = Text()
    if a.correct:
        out.append("✓ right", style=f"bold {GREEN}")
    elif a.outcome == "skipped":
        out.append("skipped", style=f"bold {DIM}")
        out.append(f" — it was {a.problem.answer_text}", style="bold")
    else:
        out.append(f"✗ {a.given}", style=f"bold {RED}")
        out.append(f" — it was {a.problem.answer_text}", style="bold")
    out.append(f"\n{a.problem.text}", style=DIM)
    for line in a.problem.explanation:
        out.append(f"\n{line}")
    if a.mistake:
        out.append(f"\n{a.mistake}", style=f"bold {AMBER}")
    return out


class ProbScreen(ClockScreen):
    BINDINGS = [
        Binding("enter", "submit", "submit", priority=True),
        Binding("backspace", "backspace", "erase", priority=True),
        Binding("s", "skip", "skip"),
        Binding("ctrl+e", "end_run", "end run", priority=True),
    ]

    DEFAULT_CSS = """
    ProbScreen #strip { height: 1; padding: 0 1; background: #1C232C; }
    ProbScreen #body { height: 1fr; }
    ProbScreen #left { width: 1fr; }
    ProbScreen #right { width: 48; }
    ProbScreen #question { padding: 1 1; }
    ProbScreen #clock { text-align: center; }
    """

    run: ProbRun

    def compose(self) -> ComposeResult:
        yield TopBar(crumb(self.run), "", None)
        yield Static(id="strip")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("QUESTION", Static(id="question"), double=True)
                yield TitledPanel("WHY", Static(id="why"), id="why-panel")
            with Vertical(id="right"):
                yield TitledPanel("CLOCK", Static(id="clock"))
                yield TitledPanel("SO FAR", Static(id="so-far"))
        yield GameKeyBar([("0–9 . - /", "type"), ("⌫", "erase"), ("⏎", "submit"), ("S", "skip"), ("^E", "end run")])

    def on_mount(self) -> None:
        self.best = load_bests().get(best_key(self.run.mode, self.run.board), {}).get("correct")
        super().on_mount()

    # ── view ────────────────────────────────────────────────────────────────

    def refresh_view(self) -> None:
        r = self.run
        strip = Text()
        strip.append("ANSWERED ", style=DIM)
        strip.append(f"{r.answered}/20", style="bold")
        strip.append("   ✓ ", style=DIM)
        strip.append(str(r.correct), style=f"bold {GREEN}")
        strip.append("   ✗ ", style=DIM)
        strip.append(str(r.wrong), style=f"bold {RED}")
        strip.append("   BEST ", style=DIM)
        strip.append(str(self.best) if self.best is not None else "—", style=f"bold {AMBER}")
        strip.append(f"   {TAGLINE}", style=DIM)
        self.query_one("#strip", Static).update(strip)
        self.query_one("#question", Static).update(self.question_text())
        last = r.last
        self.query_one("#why", Static).update(why_text(last) if last else
                                              Text("answer, and the reasoning shows here", style=DIM))
        left = r.time_left_ms
        self.query_one("#clock", Static).update(big(clock_text(left), f"bold {RED if left < 60_000 else AMBER}"))
        self.query_one("#so-far", Static).update(self.so_far_text())

    def question_text(self) -> Text:
        r = self.run
        p = r.problem
        out = Text()
        if p is None:
            return out
        out.append(f"Q{r.answered + 1}  ", style=DIM)
        out.append(f" {SUBTYPE_LABELS[p.subtype]} ", style=f"bold #000000 on {AMBER}")
        if r.ladder is not None:
            out.append(f"  prob {p.level}", style=f"bold {AMBER}")
            if r.ladder.changes:
                _, old, new = r.ladder.changes[-1]
                out.append(f"  {'▲' if new > old else '▼'} from L{old}", style=GREEN if new > old else RED)
        out.append("  whole number" if p.form == COUNT else "  a/b or 3-dp decimal", style=DIM)
        out.append("\n\n")
        out.append(p.text, style="bold")
        out.append("  =\n\n")
        out.append(f" {r.typed}".ljust(INPUT_W), style=f"bold {AMBER}")
        out.append("\n" + "━" * INPUT_W, style=AMBER)
        return out

    def so_far_text(self) -> Table | Text:
        """Newest first: the answer, yours ✓ / ✗, the question."""
        answers = self.run.answers[-SO_FAR_N:][::-1]
        if not answers:
            return Text("no answers yet", style=DIM)
        t = Table.grid(padding=(0, 1), expand=True)
        t.add_column(justify="right", no_wrap=True)
        t.add_column(no_wrap=True)
        t.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        for a in answers:
            mark, style = ("✓", GREEN) if a.correct else ("·", DIM) if a.outcome == "skipped" else ("✗", RED)
            t.add_row(Text(a.problem.answer_text, style="bold"), Text(f"{mark} {a.given or 'skip'}", style=style),
                      Text(a.problem.text, style=DIM))
        return t

    # ── input ───────────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        ch = event.character
        if ch and ch in KEYS:
            event.stop()
            event.prevent_default()
            if not self.leaving:
                self.run.type(ch)
                self.refresh_view()

    def action_backspace(self) -> None:
        self.run.backspace()
        self.refresh_view()

    def act(self, submit: bool) -> None:
        if self.leaving:
            return
        self.sync()
        if self.leaving:
            return
        done = self.run.submit() if submit else self.run.skip()
        if submit and done is None and self.run.typed:
            self.app.bell()  # not an answer yet (or not a whole number, on a counting question)
        if self.run.over:
            self.finish()
        else:
            self.refresh_view()

    def action_submit(self) -> None:
        self.act(True)

    def action_skip(self) -> None:
        self.act(False)

    def report_screen(self) -> Screen:
        return ProbReportScreen(self.run)


class ProbReportScreen(Screen):
    BINDINGS = [
        Binding("r", "again", "again"),
        Binding("l", "lobby", "lobby"),
        Binding("escape", "lobby", "lobby", show=False),
    ]

    DEFAULT_CSS = """
    ProbReportScreen #report-body { height: 1fr; padding: 0 1; }
    ProbReportScreen #tiles { height: auto; }
    ProbReportScreen .tile { width: 1fr; }
    ProbReportScreen .tile > Static { height: 7; }
    """

    def __init__(self, run: ProbRun) -> None:
        super().__init__()
        self.run = run
        self.beaten, self.last = file_arcade(run)

    def compose(self) -> ComposeResult:
        r = self.run
        yield TopBar(f"{crumb(r)} ▸ REPORT", f"SEED {r.seed}")
        if r.ended_early:
            yield Static("■ ENDED EARLY · scored on what you answered", classes="event-banner", id="ended-early")
        if self.beaten:
            yield Static("★ NEW BEST · correct", classes="event-banner", id="new-best")
        with VerticalScroll(id="report-body"):
            with Horizontal(id="tiles"):
                yield TitledPanel("SCORE", Static(self.score_tile(), id="prob-score"), classes="tile")
                yield TitledPanel("BY SUBTYPE", Static(self.subtype_table(), id="by-subtype"), classes="tile")
                yield TitledPanel("LAST 5 RUNS", Static(self.last_tile()), classes="tile")
            yield TitledPanel(f"MISSES · {len(r.misses)}", Static(self.misses_text(), id="misses"), double=True)
        yield KeyBar([("R", "again"), ("L", "lobby")])

    def score_tile(self) -> Text:
        r = self.run
        out = big(str(r.correct), f"bold {GREEN}")
        out.append(f"\nof 20 · {r.wrong} wrong · {r.skipped} skipped", style=DIM)
        if r.ladder is not None:
            out.append(f" · prob L{r.ladder.start[PROB_TRACK]} → L{r.ladder.level(PROB_TRACK)}", style=AMBER)
        return out

    def subtype_table(self) -> Table | Text:
        rows = self.run.by_subtype()
        if not rows:
            return Text("—", style=DIM)
        t = _table("TYPE", "RIGHT", "SEEN", right=("RIGHT", "SEEN"))
        for sub, right, seen in rows:
            t.add_row(SUBTYPE_LABELS[sub], f"{100 * right // seen}%", str(seen))
        return t

    def last_tile(self) -> Text:
        if not self.last:
            return Text("—", style=DIM)
        out = Text()
        for i, x in enumerate(reversed(self.last)):
            out.append(("\n" if i else "") + f"{x.get('date', '')[5:]:<6}", style=DIM)
            out.append(f"{x.get('correct', 0)} / 20", style=f"bold {AMBER}" if i == 0 else "")
        return out

    def misses_text(self) -> Text:
        misses = self.run.misses
        if not misses:
            return Text("no misses", style=f"bold {GREEN}")
        out = Text()
        for i, a in enumerate(misses):
            if i:
                out.append("\n\n")
            out.append_text(why_text(a))
            out.append(f"   {secs(a.ms)}", style=DIM)
        return out

    def action_again(self) -> None:
        start_run(self.app, self.run.config.replace(seed=None), switch=True)

    def action_lobby(self) -> None:
        to_lobby(self.app)
