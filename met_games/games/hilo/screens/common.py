"""Shared pieces of the Hi-Lo screens: top bar, the box-drawn card, and the clock bridge."""

from __future__ import annotations

from time import monotonic

from rich.table import Table
from rich.text import Text
from textual.screen import Screen

from met_games.games.hilo.engine import TICK, HiloGame
from met_games.games.hilo.model import Card
from met_games.games.sumgame.ui import ui_for
from met_games.widgets import DIM, RED, TEXT, TopBar, big_lines


class HiloTopBar(TopBar):
    """`HI/LO ▸ MODE · BET n / N · CAPITAL x`."""

    def __init__(self, crumb: str, round_text: str, right: str) -> None:
        super().__init__(crumb, round_text)
        self.right = right

    def render(self) -> Table:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=2, no_wrap=True)
        grid.add_column(justify="center", ratio=1, no_wrap=True)
        grid.add_column(justify="right", ratio=2, no_wrap=True)
        grid.add_row(f" {self.crumb}", self.round_text, f"{self.right} ")
        return grid


def top_bar(game: HiloGame, center: str | None = None) -> HiloTopBar:
    text = center or f"BET {min(game.number, game.total_bets)} / {game.total_bets}"
    return HiloTopBar(f"HI/LO ▸ {game.mode}", text, f"CAPITAL {game.capital:,}")


def card_art(card: Card | None, face_down: bool = False) -> Text:
    """A 9×7 box-drawn card; red suits in red. Face down (or no card) is hatched."""
    out = Text()
    out.append("┌───────┐\n", style=DIM)
    if face_down or card is None:
        for r in range(5):
            out.append("│", style=DIM)
            out.append("░░░?░░░" if r == 2 else "░░░░░░░", style=DIM)
            out.append("│\n", style=DIM)
    else:
        color = f"bold {RED if card.red else TEXT}"
        lab = card.label
        rows = [f"{lab:<7}", f"{card.suit:<7}", f"{card.suit:^7}", f"{card.suit:>7}", f"{lab:>7}"]
        for row in rows:
            out.append("│", style=DIM)
            out.append(row, style=color)
            out.append("│\n", style=DIM)
    out.append("└───────┘", style=DIM)
    return out


def big(text: str, style: str) -> Text:
    out = Text()
    for i, line in enumerate(big_lines(text)):
        out.append(("\n" if i else "") + line, style=style)
    return out


class HiloScreen(Screen):
    """Base: bridges real (or injected) time to the game's tick clock; moves on when the phase changes."""

    PHASES: tuple[str, ...] = ()

    def __init__(self, game: HiloGame) -> None:
        super().__init__()
        self.game = game
        self.ui = ui_for(game.config)
        self.leaving = False
        self.t0 = 0.0
        self.tick0 = 0

    def clock(self) -> float:
        """Seconds from `app.hilo_clock` if set (tests inject a fake), else monotonic."""
        return getattr(self.app, "hilo_clock", monotonic)()

    def on_mount(self) -> None:
        self.t0, self.tick0 = self.clock(), self.game.now
        self.refresh_view()
        self.ticker = self.set_interval(0.1, self.sync)

    def target_tick(self) -> int:
        return self.tick0 + int((self.clock() - self.t0) / TICK + 1e-9)

    def sync(self) -> None:
        if self.leaving:
            return
        self.game.advance_to(self.target_tick())
        if self.game.phase not in self.PHASES:
            self.leave()
            return
        self.refresh_view()

    def leave(self) -> None:
        from met_games.games.hilo.screens import screen_for

        self.leaving = True
        self.ticker.stop()
        self.app.switch_screen(screen_for(self.game))

    def refresh_view(self) -> None:
        """Redraw from the game state (subclasses)."""
