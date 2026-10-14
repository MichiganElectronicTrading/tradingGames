"""Mental Math display size: the MENTAL MATH · DISPLAY settings section (problem size, answer size) and the helpers
that draw a problem or a typed answer big. Drawing never changes input: every check runs on the raw typed string.

Fit: per problem, the biggest size up to the setting whose width fits the panel (HUGE → LARGE → NORMAL), rechecked
on every redraw (so on resize); the answer line the same way as you type. Word problems (desk, probability, counting —
anything with a letter or symbol the big fonts don't have) stay NORMAL, without comment. NORMAL draws exactly what the
screens drew before this setting existed.
"""

from __future__ import annotations

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from met_games import settings
from met_games.bigtext import GAP, HUGE, LARGE, NORMAL, ROWS, SIZES, fit, render, smaller, width
from met_games.settings_screen import Option, Section
from met_games.widgets import AMBER, BORDER, DIM

GAME = "math"
PROBLEM_SIZE, ANSWER_SIZE = "problem_size", "answer_size"
CURSOR = "▌"
BADGE_W = 5  # " 1 " plus two spaces before an Optiver-style choice
PREVIEW_PROBLEM, PREVIEW_ANSWER, PREVIEW_CHOICES = "7/8 − 0.3125", "0.5625", ("0.5625", "0.625")
INPUT_W = 18


def size_setting(key: str) -> str:
    value = settings.get(GAME, key, NORMAL)
    return value if value in SIZES else NORMAL


def problem_rows(text: str, size: str, room: int) -> list[str] | None:
    """Big rows for a problem at the biggest size up to `size` that fits `room`; None means draw it NORMAL as ever."""
    if size == NORMAL or room <= 0:
        return None
    used, rows = fit(text, size, room)
    return None if used == NORMAL else rows


def size_of(rows: list[str]) -> str:
    return {ROWS[LARGE]: LARGE, ROWS[HUGE]: HUGE}[len(rows)]


def answer_rows(typed: str, size: str, room: int) -> list[str] | None:
    """The typed answer plus a cursor, big, at the biggest size up to `size` that fits `room` (a long answer shrinks
    rather than clipping); None means NORMAL."""
    if room <= 0:
        return None
    while size != NORMAL:
        w = width(typed, size)
        if w is not None and w + (GAP if typed else 0) + 1 <= room:
            rows = render(typed, size) if typed else [""] * ROWS[size]
            return [row + (" " * GAP if typed else "") + CURSOR for row in rows]  # type: ignore[union-attr]
        size = smaller(size)
    return None


def big_text(rows: list[str], style: str) -> Text:
    out = Text()
    for i, row in enumerate(rows):
        out.append(("\n" if i else "") + row, style=style)
    return out


def answer_block(rows: list[str], input_w: int = INPUT_W) -> Text:
    """A big answer line and its underline."""
    out = Text()
    for i, row in enumerate(rows):
        out.append(("\n" if i else "") + f" {row}", style=f"bold {AMBER}")
    out.append("\n" + "━" * max(input_w, len(rows[0]) + 1), style=AMBER)
    return out


def choice_text(badge: Text, option: str, size: str, room: int) -> tuple[Text, int] | None:
    """An Optiver-style choice box's content at the biggest size that fits (the number badge stays normal), and its
    rows; None means NORMAL."""
    rows = problem_rows(option, size, room - BADGE_W)
    if rows is None:
        return None
    out = Text()
    for i, row in enumerate(rows):
        if i:
            out.append("\n" + " " * len(badge.plain))
        else:
            out.append_text(badge)
        out.append(f"  {row}", style="bold")
    return out, len(rows)


# ── the settings section ────────────────────────────────────────────────────


def sizes_panel() -> Text:
    out = Text()
    for i, (name, rows, what) in enumerate((("NORMAL", "1 row", "plain text"), ("LARGE", "3 rows", "line digits"),
                                            ("HUGE", "5 rows", "block digits"))):
        out.append(("\n" if i else "") + f"{name:<7}", style=f"bold {AMBER}")
        out.append(f" {rows} · {what}")
    return out


def good_to_know() -> Text:
    out = Text()
    for i, line in enumerate(("word problems stay plain text", "a problem that doesn't fit drops one size",
                              "⌘ + zooms the whole terminal")):
        out.append(("\n" if i else "") + "· ", style=AMBER)
        out.append(line)
    return out


def preview(values: dict[str, str], room: int) -> Group:
    """7/8 − 0.3125 at the problem size, a typed 0.5625 at the answer size, and two choice boxes."""
    room = room or 80
    problem = problem_rows(f"{PREVIEW_PROBLEM} =", values[PROBLEM_SIZE], room)
    parts: list = [Text("problem", style=DIM)]
    parts.append(big_text(problem, "bold") if problem else Text(f"{PREVIEW_PROBLEM}  =", style="bold"))
    parts.append(Text("\nyour answer", style=DIM))
    answer = answer_rows(PREVIEW_ANSWER, values[ANSWER_SIZE], room - 1)
    parts.append(answer_block(answer) if answer else
                 Text(f" {PREVIEW_ANSWER}".ljust(INPUT_W), style=f"bold {AMBER}") + Text("\n" + "━" * INPUT_W,
                                                                                          style=AMBER))
    parts.append(Text("\nchoices", style=DIM))
    grid = Table.grid(padding=(0, 1), expand=True)
    boxes = []
    for i, opt in enumerate(PREVIEW_CHOICES):
        badge = Text(f" {i + 1} ", style=f"bold #000000 on {AMBER}")
        big = choice_text(badge, opt, values[ANSWER_SIZE], room // 2 - 4)
        body = big[0] if big else badge + Text(f"  {opt}", style="bold")
        boxes.append(Panel(body, box=box.SQUARE, border_style=BORDER, padding=(0, 1)))
        grid.add_column(ratio=1)
    grid.add_row(*boxes)
    parts.append(grid)
    return Group(*parts)


MATH_DISPLAY = Section(
    game=GAME,
    title="MENTAL MATH · DISPLAY",
    options=(Option(PROBLEM_SIZE, "PROBLEM SIZE", SIZES, NORMAL), Option(ANSWER_SIZE, "ANSWER SIZE", SIZES, NORMAL)),
    note="answer size covers what you type and the Optiver-style choices",
    panels=lambda: [("SIZES", sizes_panel()), ("GOOD TO KNOW", good_to_know())],
    preview=preview,
)
