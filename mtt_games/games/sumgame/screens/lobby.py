"""Game lobby: pick a mode, see the preset table."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from mtt_games.games.sumgame.config import describe
from mtt_games.games.sumgame.screens.common import start_session, top_bar
from mtt_games.games.sumgame.screens.custom import CustomScreen
from mtt_games.games.sumgame.screens.howto import HowToScreen
from mtt_games.games.sumgame.screens.stats import StatsScreen
from mtt_games.games.sumgame.ui import GameUI
from mtt_games.widgets import AMBER, DIM, SELECTED, TITLE, KeyBar, RowList, TitledPanel, TopBar

MENU = ["EASY", "MEDIUM", "HARD", "CUSTOM…", None, "HOW TO PLAY", "STATS", "QUIT"]
MODES = ["EASY", "MEDIUM", "HARD"]


def modes_table(ui: GameUI, selected: str | None) -> Table:
    table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, pad_edge=False, expand=True)
    table.add_column("", style=DIM, no_wrap=True)
    for mode in MODES:
        hl = mode == selected
        table.add_column(mode, style=SELECTED if hl else "", header_style=SELECTED if hl else f"bold {TITLE}")
    rows = {mode: describe(cfg) for mode, cfg in ui.source.presets.items()}
    for label in rows["EASY"]:
        table.add_row(label, *(rows[m][label] for m in MODES))
    return table


class LobbyScreen(Screen):
    BINDINGS = [
        Binding("c", "custom", "custom"),
        Binding("h", "howto", "how to play"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    LobbyScreen #lobby-body { padding: 1 2; height: 1fr; }
    LobbyScreen #banner { color: #F2C14E; text-style: bold; height: auto; }
    LobbyScreen #subtitle { color: #C9D1D9; height: auto; margin: 0 0 1 0; }
    LobbyScreen #select { width: 30; margin-right: 2; }
    LobbyScreen #modes { width: 1fr; }
    LobbyScreen #lobby-panels { height: auto; }
    LobbyScreen #lobby-note { margin-top: 1; }
    """

    def __init__(self, ui: GameUI) -> None:
        super().__init__()
        self.ui = ui
        self.presets = ui.source.presets
        extras = [label for label, _ in ui.menu_extras]
        at = MENU.index("HOW TO PLAY") + 1
        self.menu = MENU[:at] + extras + MENU[at:]

    def compose(self) -> ComposeResult:
        yield top_bar(self.ui.source, self.ui.crumb, "", self.presets["EASY"].budget, id="topbar")
        with Vertical(id="lobby-body"):
            yield Static(self.ui.banner, id="banner")
            if self.ui.subtitle is not None:
                sub = Text(self.ui.subtitle, style=DIM)
            else:
                sub = Text("GAME", style=f"bold {AMBER}")
                sub.append(f" · {self.ui.tagline}", style=DIM)
            yield Static(sub, id="subtitle")
            with Horizontal(id="lobby-panels"):
                yield TitledPanel("SELECT MODE", RowList(self.menu, id="menu"), double=True, id="select")
                yield TitledPanel("MODES", Static(modes_table(self.ui, "EASY"), id="modes-table"), id="modes")
            if self.ui.lobby_note:
                yield Static(self.ui.lobby_note, id="lobby-note", classes="dim")
        yield KeyBar([("↑↓", "move"), ("⏎", "start"), ("C", "custom"), ("H", "how to play"), ("Q", "quit")])

    def on_row_list_moved(self, message: RowList.Moved) -> None:
        item = self.menu[message.index]
        self.query_one("#modes-table", Static).update(modes_table(self.ui, item if item in MODES else None))
        if item in MODES:
            self.query_one(TopBar).set(balance=self.presets[item].budget)

    def on_row_list_chosen(self, message: RowList.Chosen) -> None:
        item = self.menu[message.index]
        extras = dict(self.ui.menu_extras)
        if item in extras:
            self.app.push_screen(extras[item](self.ui))
        elif item in MODES:
            start_session(self.app, self.presets[item], item, switch=False)
        elif item == "CUSTOM…":
            self.action_custom()
        elif item == "HOW TO PLAY":
            self.action_howto()
        elif item == "STATS":
            self.app.push_screen(StatsScreen(self.ui))
        elif item == "QUIT":
            self.app.exit()

    def action_custom(self) -> None:
        self.app.push_screen(CustomScreen(self.ui))

    def action_howto(self) -> None:
        self.app.push_screen(HowToScreen(self.ui))
