"""Dice Game UI spec: banner, die widget, rules text."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from mtt_games.games.dice.engine import Die, DiceSession
from mtt_games.games.dice.events import VALUE, display_mode
from mtt_games.games.sumgame.ui import GameUI, register
from mtt_games.widgets import AMBER, DIM, TEXT

BANNER = """\
██████  ██  ██████ ███████
██   ██ ██ ██      ██
██   ██ ██ ██      █████
██   ██ ██ ██      ██
██████  ██  ██████ ███████"""

# pip positions (row, col) inside the 7×3 face
_TL, _TR, _ML, _C, _MR, _BL, _BR = (0, 1), (0, 5), (1, 1), (1, 3), (1, 5), (2, 1), (2, 5)
PIPS = {
    1: {_C},
    2: {_TL, _BR},
    3: {_TL, _C, _BR},
    4: {_TL, _TR, _BL, _BR},
    5: {_TL, _TR, _C, _BL, _BR},
    6: {_TL, _TR, _ML, _MR, _BL, _BR},
}


class DieWidget(Static):
    """A 9×5 box-drawn die with ● pips and `=value` underneath; hidden dice are ░ with a `?`.
    The "fresh" class (newly revealed) draws the frame in amber; `tag` (NEW, ×2) follows the value."""

    DEFAULT_CSS = """
    DieWidget { width: 9; height: 6; margin-right: 1; }
    """

    def __init__(self, face: int, value: int, *, face_up: bool) -> None:
        super().__init__()
        self.face, self.value, self.face_up = face, value, face_up
        self.tag = ""

    def on_mount(self) -> None:
        self._paint()

    def show(self, *, face_up: bool | None = None, fresh: bool | None = None, tag: str | None = None) -> None:
        if face_up is not None:
            self.face_up = face_up
        if fresh is not None:
            self.set_class(fresh, "fresh")
        if tag is not None:
            self.tag = tag
        self._paint()

    def _paint(self) -> None:
        frame = f"bold {AMBER}" if self.has_class("fresh") else DIM
        out = Text("┌───────┐\n", style=frame)
        for r in range(3):
            out.append("│", style=frame)
            if self.face_up:
                row = "".join("●" if (r, c) in PIPS[self.face] else " " for c in range(7))
                out.append(row, style=f"bold {TEXT}")
            else:
                out.append("░░░?░░░" if r == 1 else "░░░░░░░", style=DIM)
            out.append("│\n", style=frame)
        out.append("└───────┘\n", style=frame)
        label = Text()
        if self.face_up:
            if self.value != self.face:
                label.append(str(self.face), style=f"strike {DIM}")
            label.append(f"={self.value}", style="bold")
            if self.tag:
                label.append(f" {self.tag}", style=f"bold {AMBER}")
        label.align("center", 9)
        out.append_text(label)
        self.update(out)


def die_widget(die: Die, value: int, face_up: bool, event: str | None) -> DieWidget:
    # "value" events draw the die as its value (a high_only 1 shows 5 pips, no strikethrough);
    # "remap" events draw the rolled face and strike it through next to the value.
    shown = value if display_mode(event) == VALUE else die.face
    return DieWidget(shown, value, face_up=face_up)


DICE_UI = register(GameUI(
    session_cls=DiceSession,
    banner=BANNER,
    tagline="market-taking drill · 0.25 ticks",
    make_widget=die_widget,
    setup_rules=(
        "Each round a few fair six-sided dice are rolled. Every die is an independent roll, so seeing one "
        "tells you nothing about the others. Some dice land face up; the rest stay hidden.",
        "The round settles at the sum of ALL dice (after any market event). Prices move in 0.25 ticks.",
    ),
    fair_rules=(
        "Each hidden die is an independent roll of six equally likely faces, so:",
        "fair = face-up sum + hidden count × mean of the six faces (3.5, unless an event changes the faces).",
    ),
))
