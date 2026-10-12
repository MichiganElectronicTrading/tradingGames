"""The daily challenge screen: CORRECT, POINTS, DAILY STREAK (and time to the next daily), the rules, the card."""

from __future__ import annotations

from datetime import date, datetime, timezone
from fractions import Fraction

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math import daily, daily_v1
from met_games.games.math.screens.common import big, play_screen
from met_games.games.math.ui import RULES, DAILY_ITEM
from met_games.widgets import AMBER, DIM, GREEN, TITLE, KeyBar, TitledPanel, TopBar


def until(seconds: int) -> str:
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"


class DailyScreen(Screen):
    BINDINGS = [
        Binding("enter", "start", "start"),
        Binding("c", "card", "copy card"),
        Binding("l", "app.pop_screen", "lobby"),
        Binding("escape", "app.pop_screen", "back", show=False),
    ]

    DEFAULT_CSS = """
    DailyScreen #daily-body { height: 1fr; padding: 0 1; }
    DailyScreen #daily-tiles { height: auto; }
    DailyScreen .tile { width: 1fr; }
    DailyScreen .tile > Static { height: 7; }
    DailyScreen #daily-lower { height: auto; }
    DailyScreen #daily-rules { width: 1fr; }
    DailyScreen #daily-card { width: 1fr; }
    """

    def __init__(self, day: date | None = None, now: datetime | None = None) -> None:
        super().__init__()
        self.now = now
        self.day = day or daily.today(now)

    def compose(self) -> ComposeResult:
        yield TopBar(f"MATH ▸ DAILY #{daily.number(self.day)}", self.day.isoformat(), None)
        with Vertical(id="daily-body"):
            with Horizontal(id="daily-tiles"):
                yield TitledPanel("CORRECT", Static(id="d-correct"), classes="tile")
                yield TitledPanel("POINTS", Static(id="d-points"), classes="tile")
                yield TitledPanel("DAILY STREAK", Static(id="d-streak"), classes="tile")
            with Horizontal(id="daily-lower"):
                yield TitledPanel("RULES", Static(id="d-rules"), id="daily-rules")
                yield TitledPanel(f"CARD · {daily.VERSION}", Static(id="d-card"), double=True, id="daily-card")
        yield KeyBar([("⏎", "start"), ("C", "copy card"), ("L", "lobby")])

    def on_mount(self) -> None:
        self.refresh_view()

    def on_screen_resume(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        res = daily.result(self.day)
        played = daily.started(self.day)
        if res:
            correct = big(str(res["correct"]), f"bold {GREEN}")
            correct.append(f"\n{res['skipped']} skipped", style=DIM)
            if res.get("ended_early"):
                correct.append(" · ended early", style=f"bold {AMBER}")
            pts = big(str(res["points"]), f"bold {AMBER}")
            pts.append(f"\nbest combo ×{float(Fraction(res['best_combo'])):.1f}", style=DIM)
        else:
            correct = Text("not played yet" if not played else "started — no result saved", style=DIM)
            pts = Text("—", style=DIM)
        self.query_one("#d-correct", Static).update(correct)
        self.query_one("#d-points", Static).update(pts)
        streak = big(str(daily.streak(self.day)), f"bold {TITLE}")
        streak.append(f"\nday{'s' if daily.streak(self.day) != 1 else ''} in a row", style=DIM)
        streak.append(f" · next daily in {until(daily.seconds_to_next(self.now or datetime.now(timezone.utc)))}",
                      style=DIM)
        self.query_one("#d-streak", Static).update(streak)
        rules = Text()
        for i, line in enumerate(RULES[DAILY_ITEM]):
            rules.append(("\n" if i else "") + "· ", style=AMBER)
            rules.append(line)
        rules.append(f"\n\nseed {daily_v1.seed_for(self.day)} · frozen generator {daily.VERSION}", style=DIM)
        if not played:
            rules.append("\n⏎ to start — the clock starts at once", style=f"bold {AMBER}")
        self.query_one("#d-rules", Static).update(rules)
        card = daily.daily_card(self.day, res) if res else "finish today's daily to get your card"
        self.query_one("#d-card", Static).update(Text(card, style="bold" if res else DIM))

    def action_start(self) -> None:
        if not daily.start(self.day):
            self.app.bell()
            self.notify("you've played today's daily — one attempt per day", severity="warning")
            return
        self.app.switch_screen(play_screen(daily.new_daily_run(self.day)))

    def action_card(self) -> None:
        res = daily.result(self.day)
        if not res:
            self.app.bell()
            return
        card = daily.daily_card(self.day, res)
        if daily.copy(card):
            self.notify("score card copied")
        else:
            self.notify(card, title="pbcopy not found — your card:", timeout=20)
