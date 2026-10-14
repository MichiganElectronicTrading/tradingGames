"""Desk questions name the quantity they ask for and its sign: "P&L = ?" is signed (crossing the spread always
loses), "notional = ?" and "VWAP = ?" are positive, two-sided quotes always label the bid and the ask, and no
question asks for a "cost", "loss" or "profit". Answers stay exact: a sign is never ignored."""

import random
import re
from fractions import Fraction as F

import pytest
from textual.widgets import Static

from met_games.__main__ import build_app, parse_args
from met_games.games.math.config import SPRINT
from met_games.games.math.ladder import make_at
from met_games.games.math.problems import DESK, EASY, LEVELS, MEDIUM, SUBTYPES, accepts, make, money
from met_games.games.math.run import CORRECT, ListStream, Run
from met_games.games.math.screens.play import RunScreen

N = 3000
ASKS = {"pnl": " · P&L = ?", "spread": " · P&L = ?", "notional": " · notional = ?", "vwap": " · VWAP = ?"}
PRICE_PAIR = re.compile(r"(\S+) (\d[\d.]*) / (\S+) (\d[\d.]*)")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def desk_problems():
    for level in LEVELS:
        rng = random.Random(f"desk-{level}")
        yield level, [make(rng, DESK, level) for _ in range(N)]
    for n in range(1, 11):
        rng = random.Random(f"desk-L{n}")
        yield f"L{n}", [make_at(rng, "desk", n) for _ in range(N // 5)]


def check_sign(p):
    if p.subtype == "spread":
        bid, ask, q = p.operands
        assert p.answer == (bid - ask) * q < 0, p.text
    elif p.subtype in ("notional", "vwap"):
        assert p.answer > 0, p.text


@pytest.mark.parametrize("label, problems", list(desk_problems()), ids=lambda x: x if isinstance(x, str) else "")
def test_every_desk_question_names_its_quantity_sign_and_quote(label, problems):
    seen, signs = set(), set()
    for p in problems:
        assert p.text.endswith(ASKS[p.subtype]), p.text
        assert not re.search(r"\b(cost|loss|profit)\b", p.text), p.text
        if " / " in p.text:  # two prices quoted against each other: always labelled
            m = PRICE_PAIR.search(p.text)
            assert m and m.group(1) == "bid" and m.group(3) == "ask", p.text
        if p.subtype == "spread":
            assert "bid " in p.text and "ask " in p.text
        check_sign(p)
        seen.add(p.subtype)
        if p.subtype == "pnl":
            signs.add(p.answer > 0)
    if label in LEVELS:
        assert seen == set(SUBTYPES[DESK][label])
        assert signs == {True, False}  # P&L really is signed: both turn up


def spread_problem(level, answer):
    rng = random.Random(0)
    while True:
        p = make(rng, DESK, level, "spread")
        if p.answer == answer:
            return p


def test_minus_200_locks_on_a_spread_question_and_200_does_not():
    p = spread_problem(MEDIUM, -200)
    bid, ask, q = p.operands
    assert p.text == f"bid {money(bid)} / ask {money(ask)} · buy {q} at the ask, sell at the bid · P&L = ?"
    assert accepts(p, "-200") and not accepts(p, "200") and p.answer_text == "-200"
    run = Run(SPRINT, ListStream([p, p]), duration_ms=120_000, board=MEDIUM, seed=1)
    for ch in "200":
        assert run.type(ch) is None  # no lock on the unsigned number
    assert run.typed == "200" and not run.attempts
    for _ in range(3):
        run.backspace()
    locked = None
    for ch in "-200":
        locked = run.type(ch)
    assert locked is not None and locked.outcome == CORRECT and locked.problem.answer == F(-200)


async def test_a_pilot_run_answers_a_spread_question_with_a_negative_number():
    p = spread_problem(EASY, -200)
    app = build_app(parse_args([]))
    app.math_clock = lambda: 100.0
    async with app.run_test(size=(150, 50)) as pilot:
        run = Run(SPRINT, ListStream([p, spread_problem(MEDIUM, -200)]), duration_ms=120_000, board=EASY, seed=1)
        app.push_screen(RunScreen(run))
        await pilot.pause()
        screen = app.screen
        question = str(screen.query_one("#problem", Static).render())
        assert "bid " in question and " / ask " in question and "P&L = ?" in question
        await pilot.press("2", "0", "0")
        await pilot.pause()
        assert not run.attempts and "200" in str(screen.query_one("#problem", Static).render())
        await pilot.press("backspace", "backspace", "backspace", "minus", "2", "0", "0")
        await pilot.pause()
        assert run.attempts and run.attempts[0].outcome == CORRECT and run.attempts[0].given == "-200"
        assert "= -200" in str(screen.query_one("#last", Static).render())
