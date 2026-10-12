"""The shared pause menu. Esc on any in-game screen (everything between a game's start and its results) opens
PAUSED: R resume · L leave to lobby · Q quit met-games. While it's open the game clock is frozen — the computer
traders run off that clock, so they freeze too — and an opaque modal hides the board, so pausing can't buy free
thinking time. Leaving logs one `"abandoned": true` line to the game's history and nothing else."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen, Screen
from textual.widgets import Static

from met_games import storage
from met_games.widgets import AMBER, DIM, KeyBar, TitledPanel

MENU_KEYS = "[R] resume   [L] leave to lobby   [Q] quit met-games"
LEAVE_PROMPT = "Leave this game? Progress won't be saved. [Y/N]"


@dataclass
class _PauseState:
    total: float = 0.0  # seconds spent paused so far (subtracted from every game clock)
    since: float | None = None  # the raw clock when the current pause began


def _state(app: App) -> _PauseState:
    state = getattr(app, "_met_pause", None)
    if state is None:
        state = app._met_pause = _PauseState()
    return state


def raw_clock(app: App, attr: str | None) -> float:
    """Seconds from `app.<attr>` if set (tests inject a fake clock), else monotonic."""
    fn = getattr(app, attr, None) if attr else None
    return (fn or monotonic)()


def game_time(app: App, attr: str | None) -> float:
    """The game clock: the raw clock minus all time spent paused, frozen while the menu is open."""
    state = _state(app)
    now = state.since if state.since is not None else raw_clock(app, attr)
    return now - state.total


def freeze(app: App, attr: str | None) -> None:
    state = _state(app)
    if state.since is None:
        state.since = raw_clock(app, attr)


def unfreeze(app: App, attr: str | None) -> None:
    state = _state(app)
    if state.since is not None:
        state.total += raw_clock(app, attr) - state.since
        state.since = None


def to_lobby(app: App) -> None:
    """Pop screens until the current game's lobby (it keeps its selected mode / difficulty) is on top."""
    while len(app.screen_stack) > 1 and not getattr(app.screen, "GAME_LOBBY", False):
        app.pop_screen()


def log_abandoned(history_file: str, **fields: Any) -> None:
    storage.append_jsonl(history_file, {"ts": datetime.now().isoformat(timespec="seconds"), **fields,
                                        "abandoned": True})


class GameKeyBar(KeyBar):
    """An in-game key bar: `Esc menu` is always its last item."""

    def set_keys(self, keys) -> None:
        super().set_keys([*keys, ("Esc", "menu")])


class GameScreen(Screen):
    """Base for every in-game screen: the pause-aware clock and Esc → PAUSED. Esc is a priority binding so a
    focused text input can't swallow it."""

    CLOCK_ATTR: str | None = None  # the app attribute a test sets to inject a fake clock

    BINDINGS = [Binding("escape", "pause_menu", "menu", priority=True)]

    menu_open = False

    def clock(self) -> float:
        return game_time(self.app, self.CLOCK_ATTR)

    # ── hooks (subclasses) ─────────────────────────────────────────────────

    def clock_runs_while_paused(self) -> bool:
        return False

    def on_pause(self, paused: bool) -> None:
        """Pause / resume anything not driven by `clock()` (e.g. a feed timer)."""

    def abandon_record(self) -> tuple[str, dict[str, Any]] | None:
        """(history file, fields) for the abandoned line."""
        return None

    def leave_prompt(self) -> str:
        return LEAVE_PROMPT

    def menu_note(self) -> str:
        return ""

    # ── the menu ───────────────────────────────────────────────────────────

    def action_pause_menu(self) -> None:
        if self.menu_open or self.app.screen is not self:
            return
        self.menu_open = True
        if not self.clock_runs_while_paused():
            freeze(self.app, self.CLOCK_ATTR)
        self.on_pause(True)
        self.app.push_screen(PauseMenu(self))

    def close_menu(self) -> None:
        """Back to the game exactly where it was."""
        self.menu_open = False
        unfreeze(self.app, self.CLOCK_ATTR)
        self.on_pause(False)

    def front(self) -> None:
        """Close the menu if it's open (the game moved on under it: the daily's clock ran out)."""
        while self.app.screen is not self and len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        if self.menu_open:
            self.close_menu()

    def stop_ticker(self) -> None:
        ticker = getattr(self, "ticker", None)
        if ticker is not None:
            ticker.stop()

    def abandon(self) -> None:
        self.stop_ticker()
        record = self.abandon_record()
        if record is not None:
            log_abandoned(record[0], **record[1])

    def leave_game(self) -> None:
        """L → Y: log the abandoned line and go back to this game's lobby."""
        self.abandon()
        to_lobby(self.app)
        unfreeze(self.app, self.CLOCK_ATTR)

    def quit_game(self) -> None:
        self.abandon()
        self.app.exit()


class PauseMenu(ModalScreen):
    """PAUSED. Opaque (see theme.tcss), so the board behind it can't be read."""

    BINDINGS = [
        Binding("r", "resume", "resume"),
        Binding("l", "leave", "leave to lobby"),
        Binding("q", "quit", "quit met-games"),
        Binding("y", "confirm(True)", show=False),
        Binding("n", "confirm(False)", show=False),
        Binding("escape", "back", "resume", priority=True),
    ]

    DEFAULT_CSS = """
    PauseMenu > TitledPanel { width: 64; background: #0B0F14; padding: 1 2; }
    """

    def __init__(self, game: GameScreen) -> None:
        super().__init__()
        self.game = game
        self.confirming = False

    def compose(self) -> ComposeResult:
        yield TitledPanel("", Static(self.text(), id="pause-text"), double=True, id="pause-panel")

    def text(self) -> Text:
        out = Text("PAUSED", style=f"bold {AMBER}")
        if self.confirming:
            out.append("\n\n" + self.game.leave_prompt(), style="bold")
        else:
            out.append("\n\n" + MENU_KEYS, style="bold")
            note = self.game.menu_note()
            if note:
                out.append(f"\n\n{note}", style=f"bold {AMBER}")
        if not self.confirming and not self.game.clock_runs_while_paused():
            out.append("\n\nthe clock is stopped", style=DIM)
        return out

    def redraw(self) -> None:
        self.query_one("#pause-text", Static).update(self.text())

    def action_resume(self) -> None:
        if self.confirming:
            return
        self.app.pop_screen()
        self.game.close_menu()

    def action_back(self) -> None:
        if self.confirming:
            self.action_confirm(False)
        else:
            self.action_resume()

    def action_leave(self) -> None:
        if not self.confirming:
            self.confirming = True
            self.redraw()

    def action_quit(self) -> None:
        if not self.confirming:
            self.game.quit_game()

    def action_confirm(self, yes: bool) -> None:
        if not self.confirming:
            return
        if yes:
            self.game.leave_game()
        else:
            self.confirming = False
            self.redraw()
