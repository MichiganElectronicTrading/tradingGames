"""Hi-Lo screens. `screen_for(game)` picks the screen for the game's current phase."""

from __future__ import annotations

from textual.screen import Screen

from met_games.games.hilo.engine import BET, OVER, REVEAL, HiloGame


def screen_for(game: HiloGame) -> Screen:
    from met_games.games.hilo.screens.bet import BetScreen
    from met_games.games.hilo.screens.end import EndScreen

    return {BET: BetScreen, REVEAL: BetScreen, OVER: EndScreen}[game.phase](game)
