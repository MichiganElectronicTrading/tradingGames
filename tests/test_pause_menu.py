"""The shared pause menu, per game, on fake clocks: Esc opens PAUSED mid-game, the clock and the computer traders
stop while it's open, R resumes exactly where it was, L → N goes back to the menu, L → Y lands on that game's lobby
(selection kept) with only an abandoned line in history. Plus the Math daily exception and Outcry's Ctrl+X."""

import json
import math

import pytest
from textual.widgets import Input, Static

from met_games import storage
from met_games.__main__ import build_app, parse_args
from met_games.games.etf.screens.round import RoundScreen as EtfRoundScreen
from met_games.games.hilo.scores import SCORES_FILE
from met_games.games.hilo.screens.bet import BetScreen
from met_games.games.hilo.screens.lobby import HiloLobby
from met_games.games.math import daily
from met_games.games.math.history import BESTS_FILE, load_bests, load_history, load_runs
from met_games.games.math.screens.daily import DailyScreen
from met_games.games.math.screens.lobby import MathLobby
from met_games.games.math.screens.play import OptiverScreen, RunScreen
from met_games.games.math.screens.report import ReportScreen
from met_games.games.outcry.book import OFFER
from met_games.games.outcry.engine import OPEN, YOU
from met_games.games.outcry.screens.rounds import OpenScreen, TradingScreen
from met_games.games.sumgame.screens.recap import RecapScreen
from met_games.games.sumgame.screens.reveal import RevealScreen
from met_games.games.sumgame.screens.round import RoundScreen
from met_games.games.trade.engine import TRADERS
from met_games.games.trade.screens.settle import SettleScreen
from met_games.games.trade.screens.turns import FillsScreen, MakeScreen, TakeScreen
from met_games.pause import LEAVE_PROMPT, PauseMenu
from met_games.widgets import KeyBar, RowList

SIZE = (150, 50)
KEYS = {" ": "space", "@": "at", "-": "minus"}


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make(argv: list[str], attr: str):
    app = build_app(parse_args(argv))
    clock = FakeClock()
    setattr(app, attr, clock)
    return app, clock


def typed(text: str) -> list[str]:
    return [KEYS.get(ch, ch) for ch in text]


def menu_text(app) -> str:
    return str(app.screen.query_one("#pause-text", Static).render())


def lines(path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


async def open_menu(pilot) -> None:
    await pilot.press("escape")
    await pilot.pause()
    app = pilot.app
    assert isinstance(app.screen, PauseMenu)
    assert "[R] resume   [L] leave to lobby   [Q] quit met-games" in menu_text(app)
    assert app.screen.styles.background.a == 1  # opaque: the board behind it is hidden


async def resume(pilot) -> None:
    await pilot.press("r")
    await pilot.pause()
    assert not isinstance(pilot.app.screen, PauseMenu)


async def leave(pilot) -> None:
    """L asks once more; N goes back to the menu; L → Y leaves."""
    app = pilot.app
    await pilot.press("l")
    assert LEAVE_PROMPT in menu_text(app)
    await pilot.press("n")
    assert isinstance(app.screen, PauseMenu) and "[R] resume" in menu_text(app)
    await pilot.press("l", "y")
    await pilot.pause()


def only_abandoned(path, **fields) -> None:
    recs = lines(path)
    assert len(recs) == 1 and recs[0]["abandoned"] is True
    assert {k: recs[0][k] for k in fields} == fields
    assert storage.read_history(path.name) == []  # stats ignore it


def esc_menu_is_last(screen) -> None:
    assert str(screen.query_one(KeyBar).render()).rstrip().endswith("Esc menu")


# ── Card / Dice ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", ["card", "dice"])
async def test_sum_games_pause_resume_and_leave(isolated_home, key):
    app, clock = make([key, "--seed", "4"], "sum_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("down", "enter")  # MEDIUM
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RoundScreen) and screen.session.mode == "MEDIUM"
        esc_menu_is_last(screen)
        clock.t += 3
        screen.tick()
        assert screen.elapsed() == 3

        await open_menu(pilot)
        clock.t += 100  # far past the round timer
        screen.tick()
        await pilot.pause()
        assert screen.elapsed() == 3 and not screen.done and isinstance(app.screen, PauseMenu)
        await pilot.press("escape")  # Esc again = resume
        await pilot.pause()
        assert app.screen is screen and screen.elapsed() == 3
        clock.t += 1
        assert screen.elapsed() == 4

        await pilot.press("p")
        await pilot.pause()
        reveal = app.screen
        assert isinstance(reveal, RevealScreen) and reveal.query_one("#report-input", Input).has_focus
        esc_menu_is_last(reveal)
        await open_menu(pilot)  # Esc isn't swallowed by the P&L input
        await resume(pilot)
        assert app.screen is reveal and reveal.query_one("#report-input", Input).has_focus

        await open_menu(pilot)
        await leave(pilot)
        assert app.screen is lobby and lobby.query_one("#menu", RowList).index == 1  # MEDIUM still selected
    only_abandoned(isolated_home / f"{key}_history.jsonl", mode="MEDIUM", seed=4)


async def test_results_escape_goes_straight_to_the_lobby():
    app, clock = make(["card", "--seed", "4"], "sum_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("enter")
        await pilot.pause()
        while isinstance(app.screen, RoundScreen):
            await pilot.press("p", "0", "enter", "enter")  # pass, report 0, next
            await pilot.pause()
        assert isinstance(app.screen, RecapScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is lobby


async def test_ctrl_c_quits_from_a_text_input():
    app, clock = make(["card", "--seed", "4"], "sum_clock")
    quits = []
    app.action_quit = lambda: quits.append(True)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("enter", "p")
        await pilot.pause()
        assert app.screen.query_one("#report-input", Input).has_focus
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert quits == [True]


# ── Trading Game ────────────────────────────────────────────────────────────


def filling_quote(session) -> tuple[int, int]:
    hand = session.current
    ask = math.floor(min(hand.est(t) for t in TRADERS)) - 1
    return ask - session.config.width_min, ask


async def test_trade_pause_freezes_timers_and_the_fills_feed(isolated_home):
    app, clock = make(["trade", "--seed", "7"], "trade_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("down", "enter")  # MEDIUM
        await pilot.pause()
        while isinstance(app.screen, TakeScreen):
            await pilot.press("p", "enter")
            await pilot.pause()
        make_screen = app.screen
        assert isinstance(make_screen, MakeScreen) and make_screen.query_one("#in-bid", Input).has_focus
        clock.t += 2
        await open_menu(pilot)  # Esc from inside the bid input
        clock.t += 500
        make_screen.tick()
        assert make_screen.clock() - make_screen.started == 2 and not make_screen.done
        await resume(pilot)
        assert make_screen.query_one("#in-bid", Input).has_focus

        bid, ask = filling_quote(make_screen.session)
        await pilot.press(*typed(str(bid)), "tab", *typed(str(ask)), "enter")
        await pilot.pause()
        fills = app.screen
        assert isinstance(fills, FillsScreen) and fills.rows
        shown = fills.shown
        await open_menu(pilot)
        await pilot.pause(1.5)  # real time: the traders' feed would have moved on
        assert fills.shown == shown
        await resume(pilot)
        await pilot.pause(1.5)
        assert fills.shown > shown

        while not isinstance(app.screen, SettleScreen):
            screen = app.screen
            if isinstance(screen, MakeScreen):
                bid, ask = filling_quote(screen.session)
                await pilot.press(*typed(str(bid)), "tab", *typed(str(ask)), "enter")
            elif isinstance(screen, FillsScreen):
                await pilot.press("enter", "enter")
            else:
                await pilot.press("p", "enter")
            await pilot.pause()
        assert app.screen.query_one("#report-input", Input).has_focus
        await open_menu(pilot)  # Esc from inside the P&L input
        await leave(pilot)
        assert app.screen is lobby and lobby.query_one("#menu", RowList).index == 1
    only_abandoned(isolated_home / "trade_history.jsonl", mode="MEDIUM", seed=7)


# ── Outcry ──────────────────────────────────────────────────────────────────


async def test_outcry_pause_freezes_the_traders_and_ctrl_x_cancels_all(isolated_home):
    app, clock = make(["outcry", "--seed", "7"], "outcry_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("down", "enter")  # MEDIUM
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, OpenScreen)
        if screen.game.phase == OPEN:
            assert screen.query_one("#in-bid", Input).has_focus
            await pilot.press(*typed("380"), "tab", *typed("420"), "enter")
        else:
            await pilot.press("p")
        await pilot.pause()
        screen = app.screen
        game = screen.game
        assert isinstance(screen, TradingScreen) and screen.query_one("#cmd", Input).has_focus
        esc_menu_is_last(screen)
        clock.t += 6
        screen.sync()
        await pilot.press(*typed("b 10"), "enter", *typed("o 9999"), "enter")
        await pilot.pause()
        now, state, left = game.now, game.public(), game.seconds_left()

        await open_menu(pilot)  # Esc from inside the command line
        clock.t += 30
        screen.sync()
        assert game.now == now and game.public() == state  # no trader moved
        await resume(pilot)
        assert game.seconds_left() == left and screen.query_one("#cmd", Input).has_focus
        assert game.book.order_of(YOU, OFFER) is not None  # Esc no longer cancels
        await pilot.press("ctrl+x")
        await pilot.pause()
        assert game.you().bid is None and game.you().offer is None
        assert screen.history[-1].plain.endswith("✓ cancelled all orders")

        await open_menu(pilot)
        await leave(pilot)
        assert app.screen is lobby and lobby.query_one("#menu", RowList).index == 1
    only_abandoned(isolated_home / "outcry_history.jsonl", mode="MEDIUM", seed=7)


# ── ETF Arb ─────────────────────────────────────────────────────────────────


async def test_etf_pause_freezes_the_race(isolated_home):
    app, clock = make(["etf", "--seed", "7"], "etf_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("down", "enter")  # MEDIUM
        await pilot.pause()
        screen = app.screen
        game = screen.game
        assert isinstance(screen, EtfRoundScreen)
        esc_menu_is_last(screen)
        clock.t += 1
        screen.sync()
        now, decided, left = game.now, dict(game.round.decisions), game.seconds_left()
        await open_menu(pilot)
        clock.t += 60  # every trader would have traded and the bell rung
        screen.sync()
        assert game.now == now and game.round.decisions == decided and app.screen.__class__ is PauseMenu
        await resume(pilot)
        assert app.screen is screen and game.seconds_left() == left
        await open_menu(pilot)
        await leave(pilot)
        assert app.screen is lobby and lobby.query_one("#menu", RowList).index == 1
    only_abandoned(isolated_home / "etf_history.jsonl", mode="MEDIUM", seed=7)


# ── Hi/Lo ───────────────────────────────────────────────────────────────────


async def test_hilo_pause_and_leave_keeps_no_high_score(isolated_home):
    app, clock = make(["hilo", "--seed", "7"], "hilo_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("down")
        mode = lobby.mode
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        game = screen.game
        assert isinstance(screen, BetScreen) and game.mode == mode
        esc_menu_is_last(screen)
        clock.t += 2
        screen.sync()
        now = game.now
        await open_menu(pilot)
        clock.t += 60
        screen.sync()
        assert game.now == now
        await resume(pilot)
        assert game.now == now and app.screen is screen
        await open_menu(pilot)
        await leave(pilot)
        assert isinstance(app.screen, HiloLobby) and app.screen is lobby and lobby.mode == mode
    assert not (isolated_home / SCORES_FILE).exists()
    only_abandoned(isolated_home / "hilo_history.jsonl", mode=mode, seed=7)


# ── Mental Math ─────────────────────────────────────────────────────────────


async def test_math_pause_resume_and_leave_saves_nothing(isolated_home):
    app, clock = make(["math", "--difficulty", "hard", "--seed", "5"], "math_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        assert isinstance(lobby, MathLobby)
        await pilot.press("enter")  # SPRINT · HARD
        await pilot.pause()
        screen = app.screen
        run = screen.run
        assert isinstance(screen, RunScreen) and run.board == "hard"
        esc_menu_is_last(screen)
        clock.t += 2
        await pilot.press(*run.problem.answer_text)
        await pilot.press("minus")  # half an answer in the answer box
        await pilot.pause()
        typed_before, left, problem = run.typed, run.time_left_ms, run.problem
        assert typed_before

        await open_menu(pilot)  # Esc with a half-typed answer
        clock.t += 30
        screen.sync()
        assert run.time_left_ms == left
        await resume(pilot)
        assert (run.typed, run.time_left_ms, run.problem) == (typed_before, left, problem)
        clock.t += 1
        screen.sync()
        assert run.time_left_ms == left - 1000

        await open_menu(pilot)
        await leave(pilot)
        assert app.screen is lobby and lobby.difficulty == "hard" and lobby.mode == "sprint"
    assert load_history() == [] and load_runs() == [] and load_bests() == {}
    assert not (isolated_home / BESTS_FILE).exists()
    only_abandoned(isolated_home / "math_history.jsonl", mode="sprint", difficulty="hard", seed=5)


async def test_math_optiver_pauses_too():
    app, clock = make(["math", "--mode", "optiver", "--seed", "3"], "math_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, OptiverScreen)
        esc_menu_is_last(screen)
        clock.t += 10
        screen.sync()
        left = screen.run.time_left_ms
        await open_menu(pilot)
        await pilot.press("1")  # the options are hidden and dead while paused
        clock.t += 60
        screen.sync()
        await resume(pilot)
        assert screen.run.time_left_ms == left and screen.run.answered == 0


async def test_math_daily_clock_keeps_running_and_leaving_uses_the_attempt():
    app, clock = make(["math", "--daily"], "math_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        day = app.screen.day
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        run = screen.run
        for _ in range(2):
            clock.t += 2
            await pilot.press(*run.problem.answer_text)
            await pilot.pause()
        left = run.time_left_ms

        await open_menu(pilot)
        assert "daily clock keeps running" in menu_text(app)
        clock.t += 5
        screen.sync()
        assert run.time_left_ms == left - 5000  # not paused
        await pilot.press("l")
        assert "uses today's attempt" in menu_text(app)
        await pilot.press("y")
        await pilot.pause()
        report = app.screen
        assert isinstance(report, ReportScreen) and report.query("#ended-early")
        assert run.over and run.correct == 2
        res = daily.result(day)
        assert res["correct"] == 2 and res["ended_early"] and daily.started(day)
        assert len(load_history()) == 2  # a real (if short) attempt: logged
        await pilot.press("l", "d")
        await pilot.pause()
        assert isinstance(app.screen, DailyScreen)
        assert "ended early" in str(app.screen.query_one("#d-correct", Static).render())
        await pilot.press("enter")  # the attempt is used
        await pilot.pause()
        assert isinstance(app.screen, DailyScreen)


async def test_math_daily_clock_running_out_under_the_menu_shows_the_report():
    app, clock = make(["math", "--daily"], "math_clock")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        await open_menu(pilot)
        clock.t += 121
        screen.sync()
        await pilot.pause()
        assert isinstance(app.screen, ReportScreen) and not app.screen.query("#ended-early")
        assert len(app.screen_stack) == 3  # home, lobby, report: the menu is gone
