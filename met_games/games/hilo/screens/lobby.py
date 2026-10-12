"""Hi-Lo lobby: modes, the deck picker, the MODES table, scoring, and your best score."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.hilo.config import DECK_LABELS, DECKS, FULL, INTERVIEW, REDBLACK
from met_games.games.hilo.scores import best
from met_games.games.hilo.ui import scoring_table
from met_games.games.sumgame.screens.common import start_session
from met_games.games.sumgame.screens.custom import CustomScreen
from met_games.games.sumgame.screens.howto import HowToScreen
from met_games.games.sumgame.screens.lobby import modes_table
from met_games.games.sumgame.ui import GameUI
from met_games.widgets import AMBER, DIM, SELECTED, KeyBar, RowList, TitledPanel, TopBar

MODES = ["EASY", "MEDIUM", "HARD"]
MENU = ["EASY", "MEDIUM", "HARD", "RED/BLACK", "CUSTOM…", None, "HOW TO PLAY", "HIGH SCORES", "QUIT"]
DEFAULT_DECK = {"EASY": INTERVIEW, "MEDIUM": FULL, "HARD": FULL, "RED/BLACK": REDBLACK}
RED_BLACK_MODE = "MEDIUM"  # the RED/BLACK shortcut plays MEDIUM with the red/black deck
DECK_NOTES = {INTERVIEW: "13 cards · 12 bets", FULL: "52 cards · 51 bets", REDBLACK: "52 cards · call the color"}


class HiloLobby(Screen):
    GAME_LOBBY = True  # the pause menu's "leave to lobby" stops here
    BINDINGS = [
        Binding("d", "cycle_deck", "deck"),
        Binding("c", "custom", "custom"),
        Binding("h", "howto", "how to play"),
        Binding("s", "scores", "high scores"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    HiloLobby #lobby-body { padding: 1 2 0 2; height: 1fr; }
    HiloLobby #banner { color: #F2C14E; text-style: bold; height: auto; }
    HiloLobby #subtitle { height: auto; }
    HiloLobby #select { width: 30; margin-right: 2; }
    HiloLobby #lobby-right { width: 1fr; height: auto; }
    HiloLobby #lobby-panels { height: auto; }
    """

    def __init__(self, ui: GameUI) -> None:
        super().__init__()
        self.ui = ui
        self.presets = ui.source.presets
        self.mode = "EASY"
        self.deck = INTERVIEW
        self.picked = False  # True once you choose a deck yourself (D or --deck): it then sticks

    def compose(self) -> ComposeResult:
        yield TopBar(self.ui.crumb)
        with Vertical(id="lobby-body"):
            yield Static(self.ui.banner, id="banner")
            yield Static(id="subtitle")
            with Horizontal(id="lobby-panels"):
                yield TitledPanel("SELECT MODE", RowList(MENU, id="menu"), double=True, id="select")
                with Vertical(id="lobby-right"):
                    yield TitledPanel("DECK · D to cycle", Static(id="decks"), id="deck-panel")
                    yield TitledPanel("MODES", Static(id="modes-table"), id="modes")
                    yield TitledPanel("SCORING", Static(scoring_table(timed=False), id="scoring-table"), id="scoring")
        yield KeyBar([("↑↓", "move"), ("⏎", "start"), ("D", "deck"), ("C", "custom"), ("H", "how to play"),
                      ("S", "high scores"), ("Q", "quit")])

    def on_mount(self) -> None:
        override = getattr(self.app, "deck_override", None)
        if override in DECKS:
            self.deck, self.picked = override, True
        self.query_one("#menu", RowList).focus()
        self.refresh_panels()

    @property
    def score_mode(self) -> str:
        return RED_BLACK_MODE if self.mode == "RED/BLACK" else self.mode

    def refresh_panels(self) -> None:
        sub = Text(self.ui.subtitle or "", style=f"bold {AMBER}")
        top = best(self.deck, self.score_mode)
        where = f"{DECK_LABELS[self.deck]} · {self.score_mode}"
        sub.append(f"   best {top['score']:,} ({where})" if top else f"   no score yet on {where}", style=DIM)
        self.query_one("#subtitle", Static).update(sub)
        decks = Text()
        for i, d in enumerate(DECKS):
            if i:
                decks.append("   ")
            label = f" {DECK_LABELS[d]} "
            decks.append(label, style=SELECTED if d == self.deck else "bold")
            decks.append(f" {DECK_NOTES[d]}", style=DIM)
        self.query_one("#decks", Static).update(decks)
        selected = self.mode if self.mode in MODES else None
        self.query_one("#modes-table", Static).update(modes_table(self.ui, selected))

    def on_row_list_moved(self, message: RowList.Moved) -> None:
        item = MENU[message.index]
        if item in DEFAULT_DECK:
            self.mode = item
            if not self.picked or item == "RED/BLACK":
                self.deck = DEFAULT_DECK[item]
        self.refresh_panels()

    def action_cycle_deck(self) -> None:
        self.deck = DECKS[(DECKS.index(self.deck) + 1) % len(DECKS)]
        self.picked = True
        self.refresh_panels()

    def on_row_list_chosen(self, message: RowList.Chosen) -> None:
        item = MENU[message.index]
        if item in MODES:
            start_session(self.app, self.presets[item].replace(deck=self.deck), item, switch=False)
        elif item == "RED/BLACK":
            start_session(self.app, self.presets[RED_BLACK_MODE].replace(deck=REDBLACK), RED_BLACK_MODE, switch=False)
        elif item == "CUSTOM…":
            self.action_custom()
        elif item == "HOW TO PLAY":
            self.action_howto()
        elif item == "HIGH SCORES":
            self.action_scores()
        elif item == "QUIT":
            self.app.exit()

    def action_custom(self) -> None:
        base = self.presets.get(self.score_mode, self.presets["EASY"]).replace(deck=self.deck)
        self.app.push_screen(CustomScreen(self.ui, base))

    def action_howto(self) -> None:
        self.app.push_screen(HowToScreen(self.ui))

    def action_scores(self) -> None:
        from met_games.games.hilo.screens.end import HighScoresScreen

        self.app.push_screen(HighScoresScreen(self.deck, self.score_mode))

    def on_screen_resume(self) -> None:
        self.refresh_panels()  # a game may have set a new best
