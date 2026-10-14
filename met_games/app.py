"""The MET Games app: game registry + home screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.card.ui import CARD_UI
from met_games.games.dice.ui import DICE_UI
from met_games.games.etf.ui import ETF_UI
from met_games.games.hilo.screens.lobby import HiloLobby
from met_games.games.hilo.ui import HILO_UI
from met_games.games.math.screens.display import MATH_DISPLAY
from met_games.games.math.screens.lobby import MathLobby
from met_games.games.outcry.ui import OUTCRY_UI
from met_games.games.sumgame.screens.lobby import LobbyScreen as SumLobby
from met_games.games.trade.ui import TRADE_UI
from met_games.widgets import DIM, KeyBar, RowList, TitledPanel, TopBar


@dataclass(frozen=True)
class GameInfo:
    key: str
    title: str
    tagline: str
    lobby: Callable[[], Screen]  # builds the game's lobby screen


# Adding a game = a new package under met_games/games/ plus one line here.
GAMES: list[GameInfo] = [
    GameInfo("card", "CARD GAME", "Card Expected Value", partial(SumLobby, CARD_UI)),
    GameInfo("dice", "DICE GAME", "Smaller Tick Sizing", partial(SumLobby, DICE_UI)),
    GameInfo("trade", "TRADING GAME", "You vs. 3-4 Traders", partial(SumLobby, TRADE_UI)),
    GameInfo("outcry", "OUTCRY", "8-Player Open Outcry", partial(SumLobby, OUTCRY_UI)),
    GameInfo("etf", "ETF ARB", "Basket Arbitrage Race", partial(SumLobby, ETF_UI)),
    GameInfo("hilo", "HI/LO", "Kelly Sizing Speed Run", partial(HiloLobby, HILO_UI)),
    GameInfo("math", "MATH", "Mental Math Sprints", MathLobby),
]


# Settings sections, one or more per game (each game's own options); the Settings screen lists them in this order.
SETTINGS_SECTIONS = [MATH_DISPLAY]


class HomeScreen(Screen):
    BINDINGS = [("q", "app.quit", "quit")]

    DEFAULT_CSS = """
    HomeScreen #home-body { padding: 1 2; height: 1fr; }
    HomeScreen #home-title { color: #F2C14E; text-style: bold; height: auto; margin-bottom: 1; }
    HomeScreen #games { width: 60; }
    """

    def compose(self) -> ComposeResult:
        yield TopBar("MET GAMES")
        with Vertical(id="home-body"):
            yield Static("MET GAMES · solo trading drills · Michigan Electronic Trading", id="home-title")
            rows: list[Text | None] = []
            for g in GAMES:
                row = Text(f"{g.title:<14}", style="bold")
                row.append(g.tagline, style=DIM)
                rows.append(row)
            rows += [None, Text(f"{'SETTINGS':<14}", style="bold").append("display and more", style=DIM),
                     Text("QUIT", style="bold")]
            yield TitledPanel("GAMES", RowList(rows, id="game-list"), double=True, id="games")
        yield KeyBar([("↑↓", "move"), ("⏎", "open"), ("Q", "quit")])

    def on_row_list_chosen(self, message: RowList.Chosen) -> None:
        if message.index < len(GAMES):
            self.app.push_screen(GAMES[message.index].lobby())
        elif message.index == len(GAMES) + 1:  # SETTINGS (after the divider)
            from met_games.settings_screen import SettingsScreen

            self.app.push_screen(SettingsScreen())
        else:
            self.app.exit()


class METGamesApp(App):
    CSS_PATH = "theme.tcss"
    TITLE = "MET Games"
    ENABLE_COMMAND_PALETTE = False
    # Ctrl+C quits from anywhere (Textual would otherwise make it "copy" inside text inputs)
    BINDINGS = [Binding("ctrl+c", "quit", "quit", show=False, priority=True)]

    def __init__(self, seed: int | None = None, game: str | None = None, deck: str | None = None,
                 math_mode: str | None = None, math_difficulty: str | None = None, math_daily: bool = False) -> None:
        super().__init__()
        self.deck_override = deck  # `--deck`: the deck a game with a deck picker (hilo) starts on
        # math only: `--mode` starts that run, `--difficulty` preselects it, `--daily` opens the daily
        self.math_mode, self.math_difficulty, self.math_daily = math_mode, math_difficulty, math_daily
        # When set, every session without its own seed uses this one (`--seed`, club play, tests).
        self.seed_override = seed
        self.start_game = game  # registry key of a game whose lobby opens on launch

    def get_default_screen(self) -> Screen:
        return HomeScreen()

    def on_mount(self) -> None:
        if self.start_game is not None:
            game = next(g for g in GAMES if g.key == self.start_game)
            self.push_screen(game.lobby())

