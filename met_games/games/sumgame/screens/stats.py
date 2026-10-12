"""Stats screen: per-mode summary of a game's ~/.met_games/<game>_history.jsonl, with a clear button."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Static

from met_games import storage
from met_games.games.sumgame.stats import mode_stats, money
from met_games.games.sumgame.ui import GameUI
from met_games.widgets import DIM, TITLE, KeyBar, KeyButton, TitledPanel, TopBar, fmt_balance


def stats_table(ui: GameUI) -> Table | Text:
    rows = mode_stats(storage.read_history(ui.history_file))
    if not rows:
        return Text("no sessions yet — play one from the lobby", style=DIM)
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for col in ("MODE", "SESSIONS", "BEST FINAL", "AVG EDGE TAKEN", "REPORT ACCURACY"):
        t.add_column(col, justify="left" if col == "MODE" else "right")
    for r in rows:
        acc = "—" if r.report_accuracy is None else f"{r.report_accuracy:.0%}"
        best = fmt_balance(r.best_final, ui.source.places)
        t.add_row(r.mode, str(r.sessions), best, money(r.avg_edge_taken, 2), acc)
    return t


class ConfirmClearScreen(ModalScreen[bool]):
    """Y/N confirmation before deleting a game's session history."""

    BINDINGS = [
        Binding("y", "answer(True)", "clear"),
        Binding("n", "answer(False)", "cancel"),
        Binding("escape", "answer(False)", "cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmClearScreen > TitledPanel { width: 56; background: #0B0F14; }
    ConfirmClearScreen #confirm-buttons { height: 1; margin-top: 1; }
    """

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title_text = title

    def compose(self) -> ComposeResult:
        with TitledPanel("CLEAR STATS", double=True):
            yield Static(f"Delete all {self.title_text} session history?\nThis can't be undone.")
            with Horizontal(id="confirm-buttons"):
                yield KeyButton("[Y] CLEAR", id="yes", classes="sell")
                yield KeyButton("[N] CANCEL", id="no")

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        self.dismiss(message.button.id == "yes")

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)


class StatsScreen(Screen):
    BINDINGS = [
        Binding("c", "clear", "clear stats"),
        Binding("escape", "app.pop_screen", "back"),
        Binding("q", "app.pop_screen", "back", show=False),
    ]

    DEFAULT_CSS = """
    StatsScreen #stats-body { padding: 1 2; }
    StatsScreen #clear { margin-top: 1; }
    """

    def __init__(self, ui: GameUI) -> None:
        super().__init__()
        self.ui = ui

    def compose(self) -> ComposeResult:
        yield TopBar(f"{self.ui.crumb} ▸ STATS")
        with Vertical(id="stats-body"):
            yield TitledPanel("STATS", Static(stats_table(self.ui), id="stats-table"), double=True)
            yield Static(f"history: {storage.base_dir() / self.ui.history_file}", classes="dim")
            yield KeyButton("[C] CLEAR STATS", id="clear", classes="sell")
        yield KeyBar([("C", "clear stats"), ("Esc", "back")])

    def on_mount(self) -> None:
        self.refresh_stats()

    def has_history(self) -> bool:
        return bool(storage.read_jsonl(self.ui.history_file))

    def refresh_stats(self) -> None:
        self.query_one("#stats-table", Static).update(stats_table(self.ui))
        self.query_one("#clear", KeyButton).disabled = not self.has_history()

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        self.action_clear()

    def action_clear(self) -> None:
        if not self.has_history():
            self.notify("no stats to clear")
            return
        self.app.push_screen(ConfirmClearScreen(self.ui.source.title), self._clear_confirmed)

    def _clear_confirmed(self, yes: bool | None) -> None:
        if not yes:
            return
        storage.delete(self.ui.history_file)
        self.refresh_stats()
        self.notify(f"{self.ui.source.title} stats cleared")
