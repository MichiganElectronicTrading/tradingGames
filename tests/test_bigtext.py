"""The big-digit renderer: every supported character at every size, row counts and widths, unsupported text, the
fit fallback, and snapshots of 7/8 − 0.3125 and 0.5625 at LARGE and HUGE."""

import pytest

from met_games.bigtext import CHARSET, HUGE, LARGE, NORMAL, ROWS, SIZES, fit, render, width

SNAPSHOTS = {
    ("7/8 − 0.3125", LARGE): [
        "╺━┓   ╱ ┏━┓         ┏━┓   ╺━┓ ╺┓  ╺━┓ ┏━╸",
        "  ┃  ╱  ┣━┫   ╺━╸   ┃ ┃    ━┫  ┃  ┏━┛ ┗━┓",
        "  ╹ ╱   ┗━┛         ┗━┛ • ╺━┛ ╺┻╸ ┗━╸ ╺━┛",
    ],
    ("7/8 − 0.3125", HUGE): [
        "████    █ ▄▀▀▄            ▄▀▀▄    ▀▀▀▄  ▄█  ▄▀▀▄ ████",
        "   █   ▄▀ ▀▄▄▀            █  █       █ ▀ █     █ █   ",
        "  █   ▄▀  ▄▀▀▄    ▀▀▀▀    █  █     ▀▀█   █   ▄▀  ▀▀▀▄",
        " █   ▄▀   █  █            █  █       █   █  ▄▀      █",
        " █   ▀    ▀▄▄▀            ▀▄▄▀ ██ ▄▄▄▀ ▄▄█▄ ████ ▄▄▄▀",
    ],
    ("0.5625", LARGE): [
        "┏━┓   ┏━╸ ┏━╸ ╺━┓ ┏━╸",
        "┃ ┃   ┗━┓ ┣━┓ ┏━┛ ┗━┓",
        "┗━┛ • ╺━┛ ┗━┛ ┗━╸ ╺━┛",
    ],
    ("0.5625", HUGE): [
        "▄▀▀▄    ████ ▄▀▀▀ ▄▀▀▄ ████",
        "█  █    █    █       █ █   ",
        "█  █    ▀▀▀▄ █▀▀▄  ▄▀  ▀▀▀▄",
        "█  █       █ █  █ ▄▀      █",
        "▀▄▄▀ ██ ▄▄▄▀ ▀▄▄▀ ████ ▄▄▄▀",
    ],
}


@pytest.mark.parametrize("size", SIZES)
def test_every_character_renders_at_every_size(size):
    assert set(CHARSET) == set("0123456789+-−×/÷%,.=? ")
    for ch in CHARSET:
        rows = render(ch, size)
        assert rows is not None and len(rows) == ROWS[size], (ch, size)
        assert len({len(r) for r in rows}) == 1 and len(rows[0]) == width(ch, size)
        if size != NORMAL and ch != " ":
            assert any(r.strip() for r in rows), ch  # it draws something
    text = CHARSET * 2
    rows = render(text, size)
    assert len(rows) == ROWS[size] and all(len(r) == width(text, size) for r in rows)


def test_glyphs_and_gaps():
    assert render("-", LARGE) == render("−", LARGE) and render("-", HUGE) == render("−", HUGE)
    assert width(".", LARGE) == 1 and render(".", LARGE)[2] == "•"
    assert width("12", LARGE) == width("1", LARGE) + 1 + width("2", LARGE)  # one blank column between glyphs
    assert all(width(ch, HUGE) <= 4 for ch in CHARSET) and width("8", HUGE) == 4
    assert render("7/8", NORMAL) == ["7/8"] and width("7/8", NORMAL) == 3


@pytest.mark.parametrize("text", ["3 apples", "x", "@4", "$12", "√581", "(3)", "VWAP = ?", "1.5 + a"])
def test_unsupported_characters_give_none(text):
    assert render(text, LARGE) is None and render(text, HUGE) is None
    assert width(text, LARGE) is None and render(text, NORMAL) == [text]


@pytest.mark.parametrize("text, size", list(SNAPSHOTS))
def test_snapshots(text, size):
    assert render(text, size) == SNAPSHOTS[(text, size)]


def test_fit_drops_one_size_at_a_time():
    text = "8457 + 3916 ="  # a long HARD problem
    huge, large = width(text, HUGE), width(text, LARGE)
    assert huge > large > len(text)
    assert fit(text, HUGE, huge) == (HUGE, render(text, HUGE))
    assert fit(text, HUGE, huge - 1) == (LARGE, render(text, LARGE))
    assert fit(text, HUGE, large - 1) == (NORMAL, [text])
    assert fit(text, LARGE, huge + 50)[0] == LARGE  # never bigger than asked
    assert fit("bought 300 @ 42.10 · P&L = ?", HUGE, 500) == (NORMAL, ["bought 300 @ 42.10 · P&L = ?"])
