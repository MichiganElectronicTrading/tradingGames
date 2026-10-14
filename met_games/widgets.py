"""Shared widgets for the classic TUI look: panels, bars, cards, selectable rows, big digits."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich.table import Table
from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

TEXT = "#C9D1D9"
DIM = "#8B97A5"
BORDER = "#3FA7B5"
TITLE = "#5FD4E0"
AMBER = "#F2C14E"
GREEN = "#5BD17A"
RED = "#FF6B6B"
SELECTED = f"bold #000000 on {AMBER}"


def fmt_balance(x: Any, places: int = 0) -> str:
    return f"{'-' if x < 0 else ''}${abs(x):,.{places}f}"


class TitledPanel(Vertical):
    """A bordered panel with its title inset in the top border. `double=True` for main panels."""

    def __init__(self, title: str, *children: Widget, double: bool = False, id: str | None = None,
                 classes: str = "") -> None:
        super().__init__(*children, id=id, classes=classes)
        self.border_title = title
        if double:
            self.add_class("double")


class TopBar(Widget):
    """Reverse-video bar: breadcrumb left, round in the middle, balance right."""

    def __init__(self, crumb: str, round_text: str = "", balance: Any = None, id: str | None = None,
                 places: int = 0) -> None:
        super().__init__(id=id)
        self.crumb, self.round_text, self.balance, self.places = crumb, round_text, balance, places

    def set(self, *, crumb: str | None = None, round_text: str | None = None, balance: Any = None) -> None:
        if crumb is not None:
            self.crumb = crumb
        if round_text is not None:
            self.round_text = round_text
        if balance is not None:
            self.balance = balance
        self.refresh()

    def render(self) -> Table:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=2, no_wrap=True)
        grid.add_column(justify="center", ratio=1, no_wrap=True)
        grid.add_column(justify="right", ratio=2, no_wrap=True)
        bal = "" if self.balance is None else f"BAL {fmt_balance(self.balance, self.places)} "
        grid.add_row(f" {self.crumb}", self.round_text, bal)
        return grid


class KeyBar(Static):
    """Reverse-video key-hint bar: [(key, label), ...]."""

    def __init__(self, keys: Sequence[tuple[str, str]] = (), id: str | None = None) -> None:
        super().__init__(id=id)
        self.set_keys(keys)

    def set_keys(self, keys: Sequence[tuple[str, str]]) -> None:
        text = Text(" ")
        for i, (key, label) in enumerate(keys):
            if i:
                text.append(" · ")
            text.append(key, style="bold")
            text.append(f" {label}")
        self.update(text)


class KeyButton(Static):
    """A flat one-line button. Clicking posts KeyButton.Pressed; keyboard shortcuts live on the screen."""

    class Pressed(Message):
        def __init__(self, button: KeyButton) -> None:
            super().__init__()
            self.button = button

    def __init__(self, label: str = "", *, id: str | None = None, classes: str = "") -> None:
        super().__init__(label, markup=False, id=id, classes=classes)

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if not self.disabled:
            self.post_message(self.Pressed(self))


class RowList(Widget, can_focus=True):
    """A vertical menu of rows (None = divider). ↑↓ move, ⏎ chooses; the selected row is reverse amber."""

    BINDINGS = [
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("enter", "choose", show=False),
    ]

    class Moved(Message):
        def __init__(self, row_list: RowList, index: int) -> None:
            super().__init__()
            self.row_list, self.index = row_list, index

    class Chosen(Message):
        def __init__(self, row_list: RowList, index: int) -> None:
            super().__init__()
            self.row_list, self.index = row_list, index

    def __init__(self, rows: Sequence[str | Text | None], index: int = 0, *, id: str | None = None,
                 classes: str = "") -> None:
        super().__init__(id=id, classes=classes)
        self.rows = list(rows)
        self.index = index

    def set_rows(self, rows: Sequence[str | Text | None], index: int | None = None) -> None:
        self.rows = list(rows)
        if index is not None:
            self.index = index
        self.index = min(self.index, len(self.rows) - 1)
        self.refresh(layout=True)

    def action_move(self, delta: int) -> None:
        i = self.index
        while 0 <= i + delta < len(self.rows):
            i += delta
            if self.rows[i] is not None:
                self.index = i
                self.refresh()
                self.post_message(self.Moved(self, i))
                return

    def action_choose(self) -> None:
        self.post_message(self.Chosen(self, self.index))

    def on_click(self, event: events.Click) -> None:
        if 0 <= event.y < len(self.rows) and self.rows[event.y] is not None:
            self.index = event.y
            self.refresh()
            self.post_message(self.Moved(self, self.index))
            self.post_message(self.Chosen(self, self.index))

    def on_focus(self) -> None:
        self.refresh()

    def on_blur(self) -> None:
        self.refresh()

    def render(self) -> Text:
        width = max(self.content_size.width, 1)
        out = Text()
        for i, row in enumerate(self.rows):
            if row is None:
                line = Text("─" * width, style=DIM)
            else:
                line = Text(" ") + (row.copy() if isinstance(row, Text) else Text(row))
                line.truncate(width, pad=True)
                if i == self.index:
                    line.stylize(SELECTED if self.has_focus else f"bold {AMBER}")
            if i:
                out.append("\n")
            out.append_text(line)
        return out


class CardWidget(Static):
    """A playing card box: rank+suit top-left, `=value` bottom-right; face-down cards are ░."""

    INNER = 6

    def __init__(self, label: str, suit: str, rank: int, value: int, *, face_up: bool, red: bool) -> None:
        super().__init__()
        self.label, self.suit, self.rank, self.value, self.red = label, suit, rank, value, red
        self.face_up = face_up
        self.tag = ""

    def on_mount(self) -> None:
        self._paint()

    def show(self, *, face_up: bool | None = None, fresh: bool | None = None, tag: str | None = None) -> None:
        """Update the card. `fresh` gives it an amber border; `tag` (e.g. NEW, ×2) is printed mid-card."""
        if face_up is not None:
            self.face_up = face_up
        if fresh is not None:
            self.set_class(fresh, "fresh")
        if tag is not None:
            self.tag = tag
        self._paint()

    def _paint(self) -> None:
        w = self.INNER
        if not self.face_up:
            self.update(Text("\n".join(["░" * w] * 3), style=DIM))
            return
        top = Text(f"{self.label}{self.suit}", style=f"bold {RED if self.red else TEXT}")
        top.align("left", w)
        middle = Text(self.tag, style=f"bold {AMBER}")
        middle.align("center", w)
        bottom = Text()
        if self.value != self.rank:
            bottom.append(str(self.rank), style=f"strike {DIM}")
        bottom.append(f"={self.value}", style="bold")
        bottom.align("right", w)
        self.update(Text("\n").join([top, middle, bottom]))


# 5-row block font for big numbers (quote, timer)
_BIG = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": (" █ ", "██ ", " █ ", " █ ", "███"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    "-": ("   ", "   ", "███", "   ", "   "),
    ":": (" ", "█", " ", "█", " "),
    ".": (" ", " ", " ", " ", "█"),
    " ": (" ", " ", " ", " ", " "),
    "?": ("███", "  █", " ██", "   ", " █ "),
}
BIG_ROWS = 5


def big_lines(s: str) -> list[str]:
    """Render digits/'-'/':' as BIG_ROWS rows of block characters."""
    rows = [""] * BIG_ROWS
    for i, ch in enumerate(s):
        glyph = _BIG.get(ch, (" ", " ", ch, " ", " "))
        for r in range(BIG_ROWS):
            rows[r] += ("" if i == 0 else " ") + glyph[r]
    return rows
