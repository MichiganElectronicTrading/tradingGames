"""The MTT Games app: game registry + home screen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from mtt_games.games.card.ui import CARD_UI
from mtt_games.games.dice.ui import DICE_UI
from mtt_games.games.outcry.ui import OUTCRY_UI
from mtt_games.games.sumgame.screens.lobby import LobbyScreen as SumLobby
from mtt_games.games.trade.ui import TRADE_UI
from mtt_games.widgets import DIM, KeyBar, RowList, TitledPanel, TopBar


@dataclass(frozen=True)
class GameInfo:
    key: str
    title: str
    tagline: str
    lobby: Callable[[], Screen]  # builds the game's lobby screen


# Adding a game = a new package under mtt_games/games/ plus one line here.
GAMES: list[GameInfo] = [
    GameInfo("card", "CARD GAME", "Card Expected Value", partial(SumLobby, CARD_UI)),
    GameInfo("dice", "DICE GAME", "Smaller Tick Sizing", partial(SumLobby, DICE_UI)),
    GameInfo("trade", "TRADING GAME", "You vs. 3-4 Traders", partial(SumLobby, TRADE_UI)),
    GameInfo("outcry", "OUTCRY", "8-Player Open Outcry", partial(SumLobby, OUTCRY_UI)),
]


class HomeScreen(Screen):
    BINDINGS = [("q", "app.quit", "quit")]

    DEFAULT_CSS = """
    HomeScreen #home-body { padding: 1 2; height: 1fr; }
    HomeScreen #home-title { color: #F2C14E; text-style: bold; height: auto; margin-bottom: 1; }
    HomeScreen #games { width: 60; }
    """

    def compose(self) -> ComposeResult:
        yield TopBar("MTT GAMES")
        with Vertical(id="home-body"):
            yield Static("MTT GAMES · solo trading drills · Michigan Trading and Technology", id="home-title")
            rows = []
            for g in GAMES:
                row = Text(f"{g.title:<14}", style="bold")
                row.append(g.tagline, style=DIM)
                rows.append(row)
            yield TitledPanel("GAMES", RowList(rows, id="game-list"), double=True, id="games")
        yield KeyBar([("↑↓", "move"), ("⏎", "open"), ("Q", "quit")])

    def on_row_list_chosen(self, message: RowList.Chosen) -> None:
        self.app.push_screen(GAMES[message.index].lobby())


class MTTGamesApp(App):
    CSS_PATH = "theme.tcss"
    TITLE = "MTT Games"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, seed: int | None = None, game: str | None = None) -> None:
        super().__init__()
        # When set, every session without its own seed uses this one (`--seed`, club play, tests).
        self.seed_override = seed
        self.start_game = game  # registry key of a game whose lobby opens on launch

    def get_default_screen(self) -> Screen:
        return HomeScreen()

    def on_mount(self) -> None:
        if self.start_game is not None:
            game = next(g for g in GAMES if g.key == self.start_game)
            self.push_screen(game.lobby())

