"""Flow-style 60 in 6: the strip (answered, with ✓ / ✗ / SCORE held back until the end), QUESTION with the input,
CLOCK and PACE. Paused, the board hides but the clock keeps running — it's a test."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from met_games.games.math.flow import FlowRun
from met_games.games.math.problems import ALLOWED, FAMILY_LABELS
from met_games.games.math.screens.common import ClockScreen, big, clock_text
from met_games.pause import GameKeyBar
from met_games.widgets import AMBER, DIM, GREEN, RED, TitledPanel, TopBar

INPUT_W = 18
HIDDEN = "?"


class FlowScreen(ClockScreen):
    BINDINGS = [
        Binding("enter", "submit", "submit", priority=True),
        Binding("backspace", "backspace", "erase", priority=True),
        Binding("ctrl+e", "end_run", "end run", priority=True),
    ]

    DEFAULT_CSS = """
    FlowScreen #strip { height: 1; padding: 0 1; background: #1C232C; }
    FlowScreen #body { height: 1fr; }
    FlowScreen #left { width: 1fr; }
    FlowScreen #right { width: 40; }
    FlowScreen #question { padding: 1 1; }
    FlowScreen #clock { text-align: center; }
    """

    run: FlowRun

    def compose(self) -> ComposeResult:
        yield TopBar("MATH ▸ FLOW-STYLE 60/6", "", None)
        yield Static(id="strip")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("QUESTION", Static(id="question"), double=True)
            with Vertical(id="right"):
                yield TitledPanel("CLOCK", Static(id="clock"))
                yield TitledPanel("PACE", Static(id="pace"))
        yield GameKeyBar([("0–9 . - /", "type"), ("⌫", "erase"), ("⏎", "submit · empty skips"), ("^E", "end run")])

    # ── the test clock keeps running through the menu ───────────────────────

    def clock_runs_while_paused(self) -> bool:
        return True

    def menu_note(self) -> str:
        return "it's a test — the clock keeps running"

    # ── view ────────────────────────────────────────────────────────────────

    def refresh_view(self) -> None:
        r = self.run
        strip = Text()
        strip.append("ANSWERED ", style=DIM)
        strip.append(f"{r.answered}/{len(r.questions)}", style="bold")
        for label in ("✓", "✗", "SCORE"):
            strip.append(f"   {label} ", style=DIM)
            strip.append(HIDDEN, style=f"bold {DIM}")
        strip.append("   marked at the end · unofficial practice format", style=DIM)
        self.query_one("#strip", Static).update(strip)
        self.query_one("#question", Static).update(self.question_text())
        left = r.time_left_ms
        self.query_one("#clock", Static).update(big(clock_text(left), f"bold {RED if left < 60_000 else AMBER}"))
        self.query_one("#pace", Static).update(self.pace_text())

    def question_text(self) -> Text:
        r = self.run
        p = r.problem
        out = Text()
        if p is None:
            return out
        out.append(f"Q{r.answered + 1}  ", style=DIM)
        out.append(f" {FAMILY_LABELS[p.family]} ", style=f"bold #000000 on {AMBER}")
        hint = {"decimal": "as a decimal", "fraction": "as a fraction"}.get(p.form, "")
        out.append(f"  {hint}" if hint else "", style=DIM)
        out.append("\n\n")
        room = self.query_one("#question", Static).content_size.width
        self.problem_into(out, p.text, "  =\n\n", room)
        self.answer_into(out, r.typed, room, INPUT_W)
        return out

    def pace_text(self) -> Text:
        avg, need = self.run.pace()
        out = Text()
        out.append("your pace  ", style=DIM)
        out.append(f"{float(avg):.1f}s" if avg is not None else "—",
                   style=f"bold {GREEN if self.run.on_pace() else RED}")  # green at or under the needed pace
        out.append(" / question\nneeded     ", style=DIM)
        out.append(f"{float(need):.1f}s" if need is not None else "—", style="bold")
        out.append(" / question\n\n(time left ÷ questions left)", style=DIM)
        return out

    # ── input ───────────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        ch = event.character
        if ch and ch in ALLOWED:
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
