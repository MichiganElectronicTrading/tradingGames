"""Mental Math lobby: the MODES list (ARCADE, TEST DRILLS, MORE), the selected mode's rules, the difficulty
picker, the problem-mix toggles, the DIFFICULTY table and YOUR BESTS."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math import daily
from met_games.games.math.adaptive import stored_levels
from met_games.games.math.config import (
    ADAPTIVE,
    CHAIN,
    CUSTOM,
    DIFFICULTIES,
    ESTIMATE,
    FIXED_FORMAT,
    FLOW,
    MODE_DIFFICULTIES,
    MODE_LABELS,
    PROB_DRILL,
    STANDARD,
    SURVIVAL,
    SPRINT,
    MathConfig,
)
from met_games.games.math.history import best_fields, best_key, load_bests
from met_games.games.math.ladder import ALL_TRACKS, LEVEL_MAX, TRACK_LABELS
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

BEST_NAMES = {"correct": "correct", "points": "points", "raw": "raw score", "net": "net", "length": "longest chain"}
MIXED = (SPRINT, SURVIVAL)  # the modes the problem-mix toggles apply to


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
        Binding("s", "stats", "stats"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    MathLobby #lobby-body { padding: 1 2 0 2; height: 1fr; }
    MathLobby #banner { color: #F2C14E; text-style: bold; height: auto; }
    MathLobby #subtitle { height: auto; }
    MathLobby #lobby-panels { height: 1fr; }
    MathLobby #select { width: 34; margin-right: 2; }
    MathLobby #lobby-right { width: 1fr; height: 1fr; }
    MathLobby #pickers { height: auto; }
    MathLobby #difficulty-panel, MathLobby #mix-panel { width: 1fr; }
    MathLobby #lower-panels { height: auto; }
    MathLobby #levels-panel, MathLobby #bests-panel { width: 1fr; }
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
                with VerticalScroll(id="lobby-right"):
                    yield TitledPanel("RULES", Static(id="rules"), id="rules-panel")
                    with Horizontal(id="pickers"):
                        yield TitledPanel("DIFFICULTY · ←→", Static(id="difficulty"), id="difficulty-panel")
                        yield TitledPanel("PROBLEM MIX · 1–4", Static(id="mix"), id="mix-panel")
                    yield TitledPanel("DIFFICULTY TABLE", Static(id="table"), id="table-panel")
                    with Horizontal(id="lower-panels"):
                        yield TitledPanel("ADAPTIVE · YOUR LEVELS", Static(id="levels"), id="levels-panel")
                        yield TitledPanel("YOUR BESTS", Static(id="bests"), id="bests-panel")
        yield KeyBar([("↑↓", "mode"), ("←→", "difficulty"), ("1–4", "toggle mix"), ("⏎", "start"), ("D", "daily"),
                      ("S", "stats"), ("Q", "quit")])

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

    def options(self, mode: str | None) -> tuple[str, ...]:
        """The difficulty pills this mode offers (none for a fixed format; every one off a mode)."""
        return DIFFICULTIES if mode is None else MODE_DIFFICULTIES[mode]

    def effective(self, mode: str | None) -> str:
        """Your picked difficulty if this mode has it, else MEDIUM (the pick is kept for the modes that do)."""
        return self.difficulty if self.difficulty in self.options(mode) else MEDIUM

    def config(self, mode: str) -> MathConfig:
        return MathConfig(mode=mode, difficulty=self.effective(mode) if mode not in FIXED_FORMAT else MEDIUM,
                          families=tuple(self.families))

    # ── panels ──────────────────────────────────────────────────────────────

    def refresh_panels(self) -> None:
        kind, key, label = self.item
        mode = self.mode
        fixed = mode in FIXED_FORMAT
        current = self.effective(mode)
        self.query_one("#rules-panel").border_title = f"RULES · {label}"
        self.query_one("#rules", Static).update(howto_lines(SOON if kind == SOON else key,
                                                            adaptive=mode in MIXED and current == ADAPTIVE))
        diff = Text()
        for d in self.options(mode):
            diff.append(f" {d.upper()} ", style=SELECTED if d == current else "bold")
            diff.append(" ")
        hint = {CUSTOM: "\nCUSTOM: ⏎ opens step clock and operations" if mode == CHAIN else
                "\nCUSTOM: ⏎ opens duration, difficulty and weight per family",
                ADAPTIVE: "\nADAPTIVE: your own probability level (1–10)" if mode == PROB_DRILL else
                "\nADAPTIVE: each skill track at your own level (1–10)"}.get(current, "\n")
        diff.append("fixed format — no difficulty to pick\n" if fixed else hint, style=DIM)
        self.query_one("#difficulty", Static).update(diff)
        self.query_one("#mix", Static).update(self.mix_text(mode))
        self.query_one("#table", Static).update(difficulty_table(None if fixed else current, mode))
        self.query_one("#levels", Static).update(self.levels_text())
        self.query_one("#bests", Static).update(self.bests_text())

    def mix_text(self, mode: str | None) -> Text:
        mix = Text()
        live = mode in MIXED or mode is None
        for i, f in enumerate(FAMILIES):
            on = f in self.families
            mix.append("\n" if i == 2 else "   " if i else "")
            mix.append(f"[{i + 1}] ", style=f"bold {AMBER}" if live else DIM)
            mix.append(f"{'■' if on else '□'} {FAMILY_LABELS[f]:<5}", style="bold" if on and live else DIM)
            mix.append(f" {BASE[f]}", style=DIM)
        note = {CHAIN: "\nchains use ± × ÷ % — Custom toggles them", ESTIMATE: "\nits own five kinds of question",
                FLOW: "\ncore + decimals & fractions, medium–hard", PROB_DRILL: "\ndice · cards · coins · expected value · counting"}
        mix.append(note.get(mode, "\nfixed mix in this mode" if not live else "\nfamilies drawn evenly · base points "
                                                                              "each"), style=DIM)
        return mix

    def levels_text(self) -> Text:
        levels = stored_levels()
        if levels is None:
            return Text("no adaptive runs yet — your first one seeds each track from your history", style=DIM)
        out = Text()
        for i, t in enumerate(ALL_TRACKS):
            out.append(("\n" if i == 4 else "   " if i else "") + f"{TRACK_LABELS[t]} ", style=DIM)
            out.append(f"L{levels[t]}" if t in levels else "—", style=f"bold {AMBER}")
        out.append(f"\nlevels 1–{LEVEL_MAX} · L3 EASY · L6 MEDIUM · L9 HARD", style=DIM)
        return out

    def bests_text(self) -> Text:
        mode = self.mode
        if mode is None:
            return Text("pick a mode to see your bests", style=DIM)
        board = STANDARD if mode in FIXED_FORMAT else self.effective(mode)
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
            self.action_stats()
        elif key == QUIT_ITEM:
            self.app.exit()

    def start(self, mode: str) -> None:
        cfg = self.config(mode)
        if cfg.difficulty == CUSTOM and mode not in FIXED_FORMAT:
            from met_games.games.math.screens.custom import MathCustomScreen

            self.app.push_screen(MathCustomScreen(cfg))
            return
        start_run(self.app, cfg, switch=False)

    def action_difficulty(self, delta: int) -> None:
        options = self.options(self.mode)
        if not options:
            return
        i = options.index(self.effective(self.mode))
        self.difficulty = options[max(0, min(len(options) - 1, i + delta))]
        self.refresh_panels()

    def action_stats(self) -> None:
        from met_games.games.math.screens.stats import StatsScreen

        self.app.push_screen(StatsScreen())

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
