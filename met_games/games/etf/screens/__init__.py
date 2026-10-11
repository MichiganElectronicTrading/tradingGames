"""ETF Arb screens. `screen_for(game)` picks the screen for the game's current phase."""

from __future__ import annotations

from textual.screen import Screen

from met_games.games.etf.engine import OPEN, RECAP, RESULT, EtfGame


def screen_for(game: EtfGame) -> Screen:
    from met_games.games.etf.screens.recap import RecapScreen
    from met_games.games.etf.screens.result import ResultScreen
    from met_games.games.etf.screens.round import RoundScreen

    return {OPEN: RoundScreen, RESULT: ResultScreen, RECAP: RecapScreen}[game.phase](game)
