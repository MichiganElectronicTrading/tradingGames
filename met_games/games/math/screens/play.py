"""The run screens. Typed modes (Sprint, Survival, Zetamac, Drill, Daily): score strip, PROBLEM with the input,
LAST ANSWERS, CLOCK and BY TYPE. Optiver-style: counts, the question, four options, CLOCK and PACE."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from met_games.games.math.ladder import LEVEL_MAX, SUBTYPE_TRACK, TRACK_LABELS, TRACKS
from met_games.games.math.problems import ALLOWED, FAMILIES, FAMILY_LABELS
from met_games.games.math.run import COMBO_CAP, SKIPPED, SURVIVAL_EVERY, WRONG, points
from met_games.games.math.screens.common import ClockScreen, big, clock_text, crumb, secs
from met_games.games.math.screens.display import choice_text
from met_games.pause import GameKeyBar
from met_games.widgets import AMBER, DIM, GREEN, RED, TitledPanel, TopBar

BAR = 10
LAST_N = 6
INPUT_W = 18


def combo_bar(combo) -> Text:
    filled = round(BAR * (combo - 1) / (COMBO_CAP - 1))
    return Text("█" * filled + "░" * (BAR - filled), style=RED if combo >= 2 else AMBER)


def levels_text(ladder) -> Text:
    """Adaptive runs: every track's level now, against where it started this run, and the latest change."""
    out = Text()
    for i, t in enumerate(TRACKS):
        lv, start = ladder.level(t), ladder.start[t]
        out.append(("\n" if i else "") + f"{TRACK_LABELS[t]:<5}", style="bold")
        out.append("■" * lv + "·" * (LEVEL_MAX - lv), style=AMBER)
        out.append(f" L{lv:<2}", style="bold")
        if lv != start:
            out.append(f" {'▲' if lv > start else '▼'} from L{start}", style=GREEN if lv > start else RED)
    if ladder.changes:
        t, old, new = ladder.changes[-1]
        out.append(f"\n\nlast: {TRACK_LABELS[t]} L{old} → L{new}", style=GREEN if new > old else RED)
    return out


class RunScreen(ClockScreen):
    BINDINGS = [
        Binding("tab", "skip", "skip", priority=True),
        Binding("backspace", "backspace", "erase", priority=True),
        Binding("ctrl+e", "end_run", "end run", priority=True),
    ]

    DEFAULT_CSS = """
    RunScreen #strip { height: 1; padding: 0 1; background: #1C232C; }
    RunScreen #body { height: 1fr; }
    RunScreen #left { width: 1fr; }
    RunScreen #right { width: 40; }
    RunScreen #problem { padding: 1 1; }
    RunScreen #clock { text-align: center; }
    """

    def compose(self) -> ComposeResult:
        yield TopBar(crumb(self.run), f"SEED {self.run.seed}" if self.run.mode != "daily" else "DAILY")
        yield Static(id="strip")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("PROBLEM", Static(id="problem"), double=True, id="problem-panel")
                yield TitledPanel("LAST ANSWERS", Static(id="last"))
            with Vertical(id="right"):
                yield TitledPanel("CLOCK", Static(id="clock"))
                yield TitledPanel("LEVELS" if self.run.ladder else "BY TYPE", Static(id="by-type"))
        yield GameKeyBar([("0–9 . - /", "type"), ("⌫", "erase"), ("Tab", "skip"), ("^E", "end run")])

    # ── view ────────────────────────────────────────────────────────────────

    def refresh_view(self) -> None:
        self.query_one("#strip", Static).update(self.strip_text())
        self.query_one("#problem", Static).update(self.problem_text())
        self.query_one("#last", Static).update(self.last_text())
        self.query_one("#clock", Static).update(self.clock_panel())
        self.query_one("#by-type", Static).update(self.by_type_text())

    def strip_text(self) -> Text:
        r = self.run
        out = Text()
        out.append("CORRECT ", style=DIM)
        out.append(str(r.correct), style=f"bold {GREEN}")
        if r.scored:
            out.append("   POINTS ", style=DIM)
            out.append(f"{r.points:,}", style=f"bold {AMBER}")
            out.append("   COMBO ", style=DIM)
            out.append(f"×{float(r.combo):.1f}", style=f"bold {RED if r.combo >= 2 else AMBER}")
            out.append(f" · streak {r.streak} ", style=DIM)
            out.append_text(combo_bar(r.combo))
        else:
            out.append("   raw score — no points", style=DIM)
        return out

    def problem_text(self) -> Text:
        r = self.run
        p = r.problem
        out = Text()
        if p is None:
            return out
        out.append(f" {FAMILY_LABELS[p.family]} ", style=f"bold #000000 on {AMBER}")
        if r.ladder:
            out.append(f"  {TRACK_LABELS[SUBTYPE_TRACK[p.subtype]]} {p.level}", style=f"bold {AMBER}")
        if r.scored:
            out.append(f"  +{points(p.base, r.streak)}", style=f"bold {GREEN}")
        hint = {"decimal": "as a decimal", "fraction": "as a fraction"}.get(p.form, "")
        out.append(f"  {hint}" if hint else "", style=DIM)
        out.append("\n\n")
        room = self.query_one("#problem", Static).content_size.width
        self.problem_into(out, p.text, "  =\n\n", room)
        self.answer_into(out, r.typed, room, INPUT_W)
        return out

    def last_text(self) -> Text:
        r = self.run
        if not r.attempts:
            return Text("no answers yet", style=DIM)
        out = Text()
        for i, a in enumerate(r.attempts[-LAST_N:][::-1]):
            if i:
                out.append("\n")
            skipped = a.outcome == SKIPPED
            out.append(f"{a.problem.text} = {a.problem.answer_text}", style=DIM if skipped else "bold")
            out.append(f"   {FAMILY_LABELS[a.problem.family]} · {secs(a.ms)}", style=DIM)
            if skipped:
                out.append("   skipped", style=RED)
            elif r.scored:
                out.append(f"   +{a.points}", style=f"bold {GREEN}")
        return out

    def clock_panel(self) -> Text:
        r = self.run
        left = r.time_left_ms
        out = big(clock_text(left), f"bold {RED if left < 10_000 else AMBER}")
        if r.survival:
            out.append(f"\n\n+{r.bonus_ms / 1000:g}s per correct · skip −5s", style="bold")
            nxt = SURVIVAL_EVERY - r.correct % SURVIVAL_EVERY  # correct answers until the next drop
            out.append(f"\n−0.5s in {nxt}" if r.bonus_ms > r.bonus_floor_ms else "\nfloor", style=DIM)
        return out

    def by_type_text(self) -> Text:
        r = self.run
        if r.ladder:
            return levels_text(r.ladder)
        out = Text()
        for i, f in enumerate(FAMILIES):
            mine = [a for a in r.attempts if a.problem.family == f]
            right = [a.ms for a in mine if a.correct]
            avg = sum(right) / len(right) if right else None
            out.append(("\n" if i else "") + f"{FAMILY_LABELS[f]:<5}", style="bold")
            out.append(f"{len(right):>3} ✓", style=GREEN)
            out.append(f"   avg {secs(avg)}", style=DIM)
        return out

    # ── input ───────────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        ch = event.character
        if ch and ch in ALLOWED:
            event.stop()
            event.prevent_default()
            if self.leaving:
                return
            self.sync()
            if not self.leaving:
                self.run.type(ch)
                self.after_input()

    def action_skip(self) -> None:
        if self.leaving:
            return
        self.sync()
        if not self.leaving:
            self.run.skip()
            self.after_input()

    def action_backspace(self) -> None:
        self.run.backspace()
        self.refresh_view()

    def after_input(self) -> None:
        if self.run.over:
            self.finish()
        else:
            self.refresh_view()


class OptiverScreen(ClockScreen):
    BINDINGS = [
        *[Binding(str(i + 1), f"answer({i})", show=False) for i in range(4)],
        Binding("s", "skip", "skip"),
        Binding("ctrl+e", "end_run", "end run", priority=True),
    ]

    DEFAULT_CSS = """
    OptiverScreen #strip { height: 1; padding: 0 1; background: #1C232C; }
    OptiverScreen #body { height: 1fr; }
    OptiverScreen #left { width: 1fr; }
    OptiverScreen #right { width: 40; }
    OptiverScreen #question { padding: 1 1; }
    OptiverScreen .option-row { height: auto; }
    OptiverScreen .option { width: 1fr; height: 3; border: solid #3FA7B5; padding: 0 1; content-align: left middle; }
    OptiverScreen #clock { text-align: center; }
    """

    def compose(self) -> ComposeResult:
        yield TopBar("MATH ▸ OPTIVER-STYLE 80/8", "unofficial practice format", None)
        yield Static(id="strip")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("QUESTION", Static(id="question"), double=True)
                for row in range(2):
                    with Horizontal(classes="option-row"):
                        for col in range(2):
                            yield Static(id=f"option-{row * 2 + col}", classes="option")
            with Vertical(id="right"):
                yield TitledPanel("CLOCK", Static(id="clock"))
                yield TitledPanel("PACE", Static(id="pace"))
        yield GameKeyBar([("1–4", "answer"), ("S", "skip"), ("^E", "end run")])

    def refresh_view(self) -> None:
        r = self.run
        strip = Text()
        strip.append("ANSWERED ", style=DIM)
        strip.append(f"{r.answered}/{len(r.questions)}", style="bold")
        strip.append("   ✓ ", style=DIM)
        strip.append(str(r.correct), style=f"bold {GREEN}")
        strip.append("   ✗ ", style=DIM)
        strip.append(str(r.wrong), style=f"bold {RED}")
        strip.append("   NET ", style=DIM)
        strip.append(f"{r.net:+d}", style=f"bold {AMBER}")
        self.query_one("#strip", Static).update(strip)
        q = r.question
        if q is not None:
            head = Text(f"Q{r.i + 1}  ", style=DIM)
            head.append(f" {FAMILY_LABELS[q.problem.family]} ", style=f"bold #000000 on {AMBER}")
            head.append("\n\n")
            question = self.query_one("#question", Static)
            self.problem_into(head, q.problem.text, "  = ?", question.content_size.width, big_suffix=" = ?")
            question.update(head)
            for i, opt in enumerate(q.options):
                self.show_option(i, opt)
        left = r.time_left_ms
        self.query_one("#clock", Static).update(big(clock_text(left), f"bold {RED if left < 60_000 else AMBER}"))
        self.query_one("#pace", Static).update(self.pace_text())

    def show_option(self, i: int, opt: str) -> None:
        """A choice box: the number badge stays normal; the value at the answer size that fits this box (each box
        falls back on its own), the box growing to fit."""
        box = self.query_one(f"#option-{i}", Static)
        badge = Text(f" {i + 1} ", style=f"bold #000000 on {AMBER}")
        big = choice_text(badge, opt, self.answer_size, box.content_size.width) if self.answer_size != "normal" \
            else None
        if big is None:
            cell = badge
            cell.append(f"  {opt}", style="bold")
            if box.styles.height is not None and box.has_class("big"):
                box.styles.height = None  # back to the stylesheet's 3 rows
                box.remove_class("big")
            box.update(cell)
            return
        content, rows = big
        box.add_class("big")
        box.styles.height = rows + 2  # the border
        box.update(content)

    def pace_text(self) -> Text:
        avg, need = self.run.pace()
        out = Text()
        out.append("your average  ", style=DIM)
        out.append(f"{float(avg):.1f}s" if avg is not None else "—", style="bold")
        out.append(" / question\nneeded        ", style=DIM)
        style = f"bold {RED if avg is not None and need is not None and avg > need else GREEN}"
        out.append(f"{float(need):.1f}s" if need is not None else "—", style=style)
        out.append(" / question to finish", style=DIM)
        last = self.run.attempts[-1] if self.run.attempts else None
        if last is not None:
            out.append("\n\nlast: ", style=DIM)
            if last.outcome == WRONG:
                out.append(f"✗ {last.given} — it was {last.problem.answer_text}", style=RED)
            elif last.outcome == SKIPPED:
                out.append(f"skipped — {last.problem.answer_text}", style=DIM)
            else:
                out.append(f"✓ {last.given}", style=GREEN)
        return out

    def action_answer(self, option: int) -> None:
        if self.leaving:
            return
        self.sync()
        if not self.leaving:
            self.run.answer(option)
            self.after_input()

    def action_skip(self) -> None:
        if self.leaving:
            return
        self.sync()
        if not self.leaving:
            self.run.skip()
            self.after_input()

    def after_input(self) -> None:
        if self.run.over:
            self.finish()
        else:
            self.refresh_view()
