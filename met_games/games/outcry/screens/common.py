"""Shared pieces of the Outcry screens: the clock bridge, top bar, table strip, and WHAT YOU KNOW."""

from __future__ import annotations

from typing import Any

from rich.table import Table
from rich.text import Text
from textual.screen import Screen

from met_games.games.outcry.engine import TICK, YOU, OutcryGame
from met_games.games.outcry.model import HIGHEST, LOWEST
from met_games.games.sumgame.ui import ui_for
from met_games.pause import GameScreen
from met_games.widgets import AMBER, DIM, GREEN, RED, TopBar, big_lines


def signed(x: int) -> str:
    return f"{x:+d}"


def money(x: float, places: int = 0) -> str:
    return f"{'-' if x < 0 else '+'}${abs(x):,.{places}f}"


class OutcryTopBar(TopBar):
    """`OUTCRY ▸ MODE · ROUND r / R · PHASE · POS p · LIMIT ±L`: the right side shows position and limit."""

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


def top_bar(game: OutcryGame, phase: str) -> OutcryTopBar:
    round_text = f"ROUND {game.round.number} / {game.config.rounds} · {phase}"
    if phase in ("FINAL", "RESULTS"):
        round_text = phase
    right = f"POS {signed(game.positions[YOU])} · LIMIT ±{game.config.limit}"
    return OutcryTopBar(f"OUTCRY ▸ {game.mode}", round_text, right)


def refresh_top_bar(screen: Screen, game: OutcryGame) -> None:
    bar = screen.query_one(OutcryTopBar)
    bar.right = f"POS {signed(game.positions[YOU])} · LIMIT ±{game.config.limit}"
    bar.refresh()


def reveals_text(game: OutcryGame) -> Text:
    """REVEALED row: values in reveal order, LOWEST/HIGHEST tags, and (yours) on your own number."""
    out = Text()
    out.append("REVEALED  ", style=f"bold {DIM}")
    seen = game.you().reveals
    if not seen:
        out.append("nothing yet", style=DIM)
    for i, r in enumerate(seen):
        if i:
            out.append(" · ", style=DIM)
        if r.label:
            out.append(f"{r.label} ", style=f"bold {AMBER}")
        out.append(str(r.value), style="bold")
        if r.mine:
            out.append(" (yours)", style=f"bold {GREEN}")
    return out


def table_strip(game: OutcryGame) -> Table:
    """8 seats: name and public net position; only your seat shows a number (yours)."""
    t = Table.grid(expand=True, padding=(0, 1))
    for _ in game.names:
        t.add_column(justify="center", ratio=1)
    names, numbers, positions = [], [], []
    for seat, name in enumerate(game.names):
        mine = seat == YOU
        names.append(Text(name, style=f"bold {AMBER}" if mine else "bold"))
        numbers.append(Text(f"[{game.setup.numbers[YOU]}]" if mine else "[ ? ]", style=f"bold {AMBER}" if mine else DIM))
        pos = game.positions[seat]
        positions.append(Text(signed(pos), style=GREEN if pos > 0 else RED if pos < 0 else DIM))
    t.add_row(*names)
    t.add_row(*numbers)
    t.add_row(*positions)
    return t


def seat_line(game: OutcryGame) -> Text:
    """The outcry's one-line seat strip."""
    out = Text(" ")
    for seat, name in enumerate(game.names):
        if seat:
            out.append(" · ", style=DIM)
        mine = seat == YOU
        out.append(name, style=f"bold {AMBER}" if mine else "bold")
        if mine:
            out.append(f"({game.setup.numbers[YOU]})", style=AMBER)
        pos = game.positions[seat]
        out.append(f" {signed(pos)}", style=GREEN if pos > 0 else RED if pos < 0 else DIM)
    out.append("   ")
    out.append_text(reveals_text(game))
    return out


def know_text(game: OutcryGame) -> Text:
    """WHAT YOU KNOW, per the helper level: EASY range seen + exact fair, MEDIUM range seen, HARD off."""
    you = game.you()
    helper = game.config.helper
    out = Text()
    out.append("your number  ", style=DIM)
    out.append(str(you.number), style=f"bold {AMBER}")
    revealed = len(you.reveals)
    out.append(f"\nrevealed     {revealed} of {game.config.players}", style=DIM)
    labels = {r.label: r.value for r in you.reveals if r.label}
    for label in (LOWEST, HIGHEST):
        if label in labels:
            out.append(f"\n{label.lower():<12} ", style=DIM)
            out.append(str(labels[label]), style="bold")
    if helper == "off":
        out.append("\nhelper off — do the math yourself", style=DIM)
        return out
    lo, hi = you.fair.range_seen
    out.append("\nrange seen   ", style=DIM)
    out.append(f"{lo}–{hi}", style="bold")
    if helper == "fair":
        out.append("\nexact fair   ", style=DIM)
        out.append(f"{you.fair.fair:.1f}", style=f"bold {GREEN}")
    return out


def clock_text(seconds: float | None, total: float) -> Text:
    secs = 0 if seconds is None else int(-(-seconds // 1))
    color = RED if (seconds or 0) < 5 else AMBER
    out = Text()
    for i, line in enumerate(big_lines(f"{secs // 60:02d}:{secs % 60:02d}")):
        out.append(("\n" if i else "") + line, style=f"bold {color}")
    width = 24
    filled = round(width * (seconds or 0) / total) if total else 0
    out.append("\n" + "█" * filled, style=color)
    out.append("░" * (width - filled), style=DIM)
    return out


def big(text: str, style: str) -> Text:
    out = Text()
    for i, line in enumerate(big_lines(text)):
        out.append(("\n" if i else "") + line, style=style)
    return out


class OutcryScreen(GameScreen):
    """Base: bridges real (or injected: `app.outcry_clock`) time to the game's tick clock, and moves to the next
    screen when the game's phase leaves the ones this screen shows. Paused, that clock (and every trader) stops."""

    PHASES: tuple[str, ...] = ()
    CLOCK_ATTR = "outcry_clock"

    DEFAULT_CSS = """
    OutcryScreen #body { height: 1fr; }
    OutcryScreen #left { width: 1fr; }
    OutcryScreen #right { width: 44; }
    OutcryScreen .timer { text-align: center; }
    """

    def __init__(self, game: OutcryGame) -> None:
        super().__init__()
        self.game = game
        self.ui = ui_for(game.config)
        self.leaving = False
        self.t0 = 0.0
        self.tick0 = 0

    def on_mount(self) -> None:
        self.t0, self.tick0 = self.clock(), self.game.now
        self.refresh_view()
        self.ticker = self.set_interval(0.1, self.sync)

    def sync(self) -> None:
        if self.leaving:
            return
        self.game.advance_to(self.tick0 + int((self.clock() - self.t0) / TICK + 1e-9))
        if self.game.phase not in self.PHASES:
            self.leave()
            return
        self.refresh_view()

    def abandon_record(self) -> tuple[str, dict[str, Any]]:
        return self.ui.history_file, {"mode": self.game.mode, "seed": self.game.seed}

    def leave(self) -> None:
        from met_games.games.outcry.screens import screen_for

        self.leaving = True
        self.ticker.stop()
        self.app.switch_screen(screen_for(self.game))

    def refresh_view(self) -> None:
        """Redraw from the game state (subclasses)."""

