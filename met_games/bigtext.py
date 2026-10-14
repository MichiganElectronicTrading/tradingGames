"""Big-digit text for problems and answers: NORMAL (1 row, the text itself), LARGE (3 rows of line digits — Textual's
bold 3×3 Digits glyphs plus the ones it lacks) and HUGE (5 rows of block digits). Pure rendering: no Textual app logic.

Only numbers and arithmetic render big: 0–9 + - − × / ÷ % , . = ? and space. Any other character (a letter, @, $, √,
brackets) makes `render` return None, and the caller shows the text at NORMAL instead.
"""

from __future__ import annotations

from textual.renderables.digits import DIGITS, DIGITS3X3_BOLD

NORMAL, LARGE, HUGE = "normal", "large", "huge"
SIZES = (NORMAL, LARGE, HUGE)
ROWS = {NORMAL: 1, LARGE: 3, HUGE: 5}
CHARSET = "0123456789+-−×/÷%,.=? "
GAP = 1  # blank columns between glyphs


def _textual(ch: str) -> list[str]:
    """One of Textual's bold 3×3 glyphs, padded to 3 columns."""
    i = DIGITS.index(ch)
    return [row.ljust(3) for row in DIGITS3X3_BOLD[i * 3:i * 3 + 3]]


_LARGE: dict[str, list[str]] = {ch: _textual(ch) for ch in "0123456789+-"}
_LARGE.update({
    "×": _textual("x"),
    "−": _textual("-"),  # U+2212 draws like -
    "/": ["  ╱", " ╱ ", "╱  "],
    "÷": [" • ", "╺━╸", " • "],
    "%": ["• ╱", " ╱ ", "╱ •"],
    ",": [" ", " ", ","],
    ".": [" ", " ", "•"],
    "=": ["   ", "╺━╸", "╺━╸"],
    "?": ["╺━┓", " ┏┛", " ╹ "],
    " ": [" ", " ", " "],
})

_HUGE: dict[str, list[str]] = {
    "0": ["▄▀▀▄", "█  █", "█  █", "█  █", "▀▄▄▀"],
    "1": [" ▄█ ", "▀ █ ", "  █ ", "  █ ", "▄▄█▄"],
    "2": ["▄▀▀▄", "   █", " ▄▀ ", "▄▀  ", "████"],
    "3": ["▀▀▀▄", "   █", " ▀▀█", "   █", "▄▄▄▀"],
    "4": ["█  █", "█  █", "▀▀▀█", "   █", "   █"],
    "5": ["████", "█   ", "▀▀▀▄", "   █", "▄▄▄▀"],
    "6": ["▄▀▀▀", "█   ", "█▀▀▄", "█  █", "▀▄▄▀"],
    "7": ["████", "   █", "  █ ", " █  ", " █  "],
    "8": ["▄▀▀▄", "▀▄▄▀", "▄▀▀▄", "█  █", "▀▄▄▀"],
    "9": ["▄▀▀▄", "█  █", "▀▄▄█", "   █", "▄▄▄▀"],
    "+": ["   ", " █ ", "███", " █ ", "   "],
    "-": ["    ", "    ", "▀▀▀▀", "    ", "    "],
    "×": ["    ", "▀▄▄▀", " ██ ", "▄▀▀▄", "    "],
    "/": ["   █", "  ▄▀", " ▄▀ ", "▄▀  ", "▀   "],
    "÷": ["    ", " ▄▄ ", "▀▀▀▀", " ▀▀ ", "    "],
    "%": ["█  ▄", "  ▄▀", " ▄▀ ", "▄▀  ", "▀  █"],
    ",": ["  ", "  ", "  ", " ▄", "▄▀"],
    ".": ["  ", "  ", "  ", "  ", "██"],
    "=": ["    ", "▄▄▄▄", "    ", "▀▀▀▀", "    "],
    "?": ["▄▀▀▄", "   █", " ▄▀ ", "    ", " ▀  "],
    " ": ["  ", "  ", "  ", "  ", "  "],
}
_HUGE["−"] = _HUGE["-"]

FONTS = {LARGE: _LARGE, HUGE: _HUGE}


def supported(text: str) -> bool:
    return all(ch in CHARSET for ch in text)


def render(text: str, size: str) -> list[str] | None:
    """The text as 1 (NORMAL), 3 (LARGE) or 5 (HUGE) equal-width rows; None if a character can't render big."""
    if size == NORMAL:
        return [text]
    if not supported(text):
        return None
    font = FONTS[size]
    rows = [""] * ROWS[size]
    for i, ch in enumerate(text):
        for r, part in enumerate(font[ch]):
            rows[r] += (" " * GAP if i else "") + part
    return rows


def width(text: str, size: str) -> int | None:
    """Columns `render(text, size)` takes; None if it can't render."""
    if size == NORMAL:
        return len(text)
    if not supported(text):
        return None
    font = FONTS[size]
    return sum(len(font[ch][0]) for ch in text) + GAP * max(0, len(text) - 1)


def smaller(size: str) -> str:
    return SIZES[max(0, SIZES.index(size) - 1)]


def fit(text: str, size: str, room: int) -> tuple[str, list[str]]:
    """The biggest size up to `size` that renders and fits in `room` columns (dropping a size at a time), and its
    rows. NORMAL always answers: the text as it is."""
    while size != NORMAL:
        w = width(text, size)
        if w is not None and w <= room:
            return size, render(text, size)  # type: ignore[return-value]
        size = smaller(size)
    return NORMAL, [text]
