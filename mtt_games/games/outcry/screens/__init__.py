"""Outcry screens. `screen_for(game)` picks the screen for the game's current phase."""

from __future__ import annotations

from textual.screen import Screen

from mtt_games.games.outcry.engine import CLOSED, OPEN, OUTCRY, REPORT, RESPOND, RESULTS, OutcryGame


def screen_for(game: OutcryGame) -> Screen:
    from mtt_games.games.outcry.screens.end import FinalScreen, ResultsScreen
    from mtt_games.games.outcry.screens.rounds import CloseScreen, OpenScreen, TradingScreen

    return {
        OPEN: OpenScreen, RESPOND: OpenScreen, OUTCRY: TradingScreen, CLOSED: CloseScreen, REPORT: FinalScreen,
        RESULTS: ResultsScreen,
    }[game.phase](game)
