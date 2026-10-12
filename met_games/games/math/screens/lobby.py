"""Mental Math lobby: the MODES list (ARCADE, TEST DRILLS, MORE), the selected mode's rules, the difficulty
picker, the problem-mix toggles, the DIFFICULTY table and YOUR BESTS."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math import daily
from met_games.games.math.config import CUSTOM, DIFFICULTIES, FIXED_FORMAT, MODE_LABELS, STANDARD, MathConfig
from met_games.games.math.history import best_fields, best_key, load_bests
from met_games.games.math.problems import BASE, FAMILIES, FAMILY_LABELS, MEDIUM
from met_games.games.math.screens.common import start_run
from met_games.games.math.ui import (
    BANNER,
    DAILY_ITEM,
    MENU,
    QUIT_ITEM,
    SOON,
    STATS_ITEM,
    SUBTITLE,
    difficulty_table,
    howto_lines,
)
from met_games.widgets import AMBER, DIM, GREEN, SELECTED, TITLE, KeyBar, RowList, TitledPanel, TopBar

BEST_NAMES = {"correct": "correct", "points": "points", "raw": "raw score", "net": "net"}


class SectionList(RowList):
    """A RowList whose section titles and "soon" rows can't be selected."""

    def __init__(self, rows, selectable: list[bool], index: int, **kw) -> None:
        super().__init__(rows, index, **kw)
        self.selectable = selectable

    def action_move(self, delta: int) -> None:
        i = self.index
        while 0 <= i + delta < len(self.rows):
            i += delta
            if self.selectable[i]:
                self.index = i
                self.refresh()
                self.post_message(self.Moved(self, i))
                return

    def on_click(self, event: events.Click) -> None:
        if 0 <= event.y < len(self.rows) and self.selectable[event.y]:
            super().on_click(event)


def menu_rows(daily_unplayed: bool) -> list[Text]:
    rows = []
    for kind, key, label in MENU:
        if kind == "head":
            rows.append(Text(label, style=f"bold {TITLE}"))
        elif kind == SOON:
            rows.append(Text(f"  {label:<20}", style=DIM).append("soon", style=f"italic {DIM}"))
        else:
            row = Text(f"  {label}", style="bold")
            if key == DAILY_ITEM and daily_unplayed:
                row.append(" ●", style=f"bold {AMBER}")
            rows.append(row)
    return rows


class MathLobby(Screen):
    GAME_LOBBY = True  # the pause menu's "leave to lobby" stops here
    BINDINGS = [
        Binding("left", "difficulty(-1)", "easier", priority=True),
        Binding("right", "difficulty(1)", "harder", priority=True),
        *[Binding(str(i + 1), f"toggle({i})", show=False) for i in range(4)],
        Binding("d", "daily", "daily"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    MathLobby #lobby-body { padding: 1 2 0 2; height: 1fr; }
    MathLobby #banner { color: #F2C14E; text-style: bold; height: auto; }
    MathLobby #subtitle { height: auto; }
    MathLobby #lobby-panels { height: auto; }
    MathLobby #select { width: 34; margin-right: 2; }
    MathLobby #lobby-right { width: 1fr; height: auto; }
    MathLobby #pickers { height: auto; }
    MathLobby #difficulty-panel, MathLobby #mix-panel { width: 1fr; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.index = next(i for i, (kind, _, _) in enumerate(MENU) if kind == "mode")
        self.difficulty = MEDIUM
        self.families = list(FAMILIES)
        self.custom: MathConfig | None = None

    def compose(self) -> ComposeResult:
        yield TopBar("MET GAMES ▸ MATH")
        with Vertical(id="lobby-body"):
            yield Static(BANNER, id="banner")
            yield Static(Text(SUBTITLE, style=f"bold {AMBER}"), id="subtitle")
            with Horizontal(id="lobby-panels"):
                selectable = [kind not in ("head", SOON) for kind, _, _ in MENU]
                yield TitledPanel("MODES", SectionList(menu_rows(self.daily_unplayed()), selectable, self.index,
                                                       id="menu"), double=True, id="select")
                with Vertical(id="lobby-right"):
                    yield TitledPanel("RULES", Static(id="rules"), id="rules-panel")
                    with Horizontal(id="pickers"):
                        yield TitledPanel("DIFFICULTY · ←→", Static(id="difficulty"), id="difficulty-panel")
                        yield TitledPanel("PROBLEM MIX · 1–4", Static(id="mix"), id="mix-panel")
                    yield TitledPanel("DIFFICULTY TABLE", Static(id="table"), id="table-panel")
                    yield TitledPanel("YOUR BESTS", Static(id="bests"), id="bests-panel")
        yield KeyBar([("↑↓", "mode"), ("←→", "difficulty"), ("1–4", "toggle mix"), ("⏎", "start"), ("D", "daily"),
                      ("Q", "quit")])

    def daily_unplayed(self) -> bool:
        return not daily.started(daily.today())

    def on_mount(self) -> None:
        self.query_one("#menu", SectionList).focus()
        app = self.app
        if getattr(app, "math_difficulty", None) in DIFFICULTIES:
            self.difficulty = app.math_difficulty
        self.refresh_panels()
        if getattr(app, "math_daily", False):
            app.math_daily = False
            self.action_daily()
        elif getattr(app, "math_mode", None):
            mode, app.math_mode = app.math_mode, None
            self.select(mode)
            self.start(mode)

    def on_screen_resume(self) -> None:
        self.query_one("#menu", SectionList).set_rows(menu_rows(self.daily_unplayed()))
        self.refresh_panels()

    # ── state ───────────────────────────────────────────────────────────────

    @property
    def item(self) -> tuple[str, str, str]:
        return MENU[self.index]

    @property
    def mode(self) -> str | None:
        kind, key, _ = self.item
        return key if kind == "mode" else None

    def select(self, key: str) -> None:
        self.index = next(i for i, (_, k, _) in enumerate(MENU) if k == key)
        self.query_one("#menu", SectionList).index = self.index
        self.query_one("#menu", SectionList).refresh()
        self.refresh_panels()

    def config(self, mode: str) -> MathConfig:
        return MathConfig(mode=mode, difficulty=self.difficulty if mode not in FIXED_FORMAT else MEDIUM,
                          families=tuple(self.families))

    # ── panels ──────────────────────────────────────────────────────────────

    def refresh_panels(self) -> None:
        kind, key, label = self.item
        self.query_one("#rules-panel").border_title = f"RULES · {label}"
        self.query_one("#rules", Static).update(howto_lines(SOON if kind == SOON else key))
        fixed = self.mode in FIXED_FORMAT
        diff = Text()
        for d in DIFFICULTIES:
            style = SELECTED if d == self.difficulty and not fixed else (DIM if fixed else "bold")
            diff.append(f" {d.upper()} ", style=style)
            diff.append(" ")
        diff.append("\nfixed format — the picker doesn't apply" if fixed else
                    "\nCUSTOM: ⏎ opens duration, difficulty and weight per family" if self.difficulty == CUSTOM
                    else "\n", style=DIM)
        self.query_one("#difficulty", Static).update(diff)
        mix = Text()
        for i, f in enumerate(FAMILIES):
            on = f in self.families
            mix.append("\n" if i == 2 else "   " if i else "")
            mix.append(f"[{i + 1}] ", style=f"bold {AMBER}")
            mix.append(f"{'■' if on else '□'} {FAMILY_LABELS[f]:<5}", style="bold" if on else DIM)
            mix.append(f" {BASE[f]}", style=DIM)
        mix.append("\nfixed mix in this mode" if fixed else "\nfamilies drawn evenly · base points each",
                   style=DIM)
        self.query_one("#mix", Static).update(mix)
        self.query_one("#table", Static).update(difficulty_table(None if fixed else self.difficulty))
        self.query_one("#bests", Static).update(self.bests_text())

    def bests_text(self) -> Text:
        mode = self.mode
        if mode is None:
            return Text("pick a mode to see your bests", style=DIM)
        board = STANDARD if mode in FIXED_FORMAT else self.difficulty
        entry = load_bests().get(best_key(mode, board), {})
        out = Text(f"{MODE_LABELS[mode]} · {board.upper()}\n", style="bold")
        for i, f in enumerate(best_fields(mode)):
            out.append(("   " if i else "") + f"{BEST_NAMES[f]} ", style=DIM)
            out.append(f"{entry[f]:,}" if f in entry else "—", style=f"bold {GREEN if f in entry else DIM}")
        return out

    # ── keys ────────────────────────────────────────────────────────────────

    def on_row_list_moved(self, message: RowList.Moved) -> None:
        self.index = message.index
        self.refresh_panels()

    def on_row_list_chosen(self, message: RowList.Chosen) -> None:
        kind, key, _ = MENU[message.index]
        if kind == "mode":
            self.start(key)
        elif key == DAILY_ITEM:
            self.action_daily()
        elif key == STATS_ITEM:
            from met_games.games.math.screens.stats import StatsScreen

            self.app.push_screen(StatsScreen())
        elif key == QUIT_ITEM:
            self.app.exit()

    def start(self, mode: str) -> None:
        cfg = self.config(mode)
        if self.difficulty == CUSTOM and mode not in FIXED_FORMAT:
            from met_games.games.math.screens.custom import MathCustomScreen

            self.app.push_screen(MathCustomScreen(cfg))
            return
        start_run(self.app, cfg, switch=False)

    def action_difficulty(self, delta: int) -> None:
        i = DIFFICULTIES.index(self.difficulty)
        self.difficulty = DIFFICULTIES[max(0, min(len(DIFFICULTIES) - 1, i + delta))]
        self.refresh_panels()

    def action_toggle(self, i: int) -> None:
        f = FAMILIES[i]
        if f in self.families:
            if len(self.families) == 1:
                self.app.bell()
                self.notify("keep at least one family on", severity="warning")
                return
            self.families.remove(f)
        else:
            self.families = [x for x in FAMILIES if x in self.families or x == f]
        self.refresh_panels()

    def action_daily(self) -> None:
        from met_games.games.math.screens.daily import DailyScreen

        self.app.push_screen(DailyScreen())
