"""Outcry Pilot tests, driven by a fake clock: the app reads `app.outcry_clock`, so nothing waits on real time."""

import json

import pytest
from textual.widgets import Input, Static

from mtt_games.__main__ import build_app, parse_args
from mtt_games.app import MTTGamesApp
from mtt_games.games.outcry.book import BID, OFFER
from mtt_games.games.outcry.engine import YOU
from mtt_games.games.outcry.screens.end import FinalScreen, ResultsScreen, TapeScreen
from mtt_games.games.outcry.screens.rounds import CloseScreen, OpenScreen, TradingScreen
from mtt_games.games.outcry.ui import CommandsScreen
from mtt_games.games.sumgame.screens.custom import CustomScreen
from mtt_games.games.sumgame.screens.howto import HowToScreen
from mtt_games.games.sumgame.screens.lobby import LobbyScreen

SIZE = (150, 50)
KEYS = {" ": "space", "@": "at", "-": "minus"}


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTT_GAMES_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def typed(text: str) -> list[str]:
    return [KEYS.get(ch, ch) for ch in text]


async def wait(pilot, clock: FakeClock, seconds: float) -> None:
    """Move the fake clock and let the screen catch the game up to it."""
    clock.t += seconds
    pilot.app.screen.sync()
    await pilot.pause()


async def until(pilot, clock: FakeClock, ready, limit: float = 20) -> None:
    """Advance the fake clock a second at a time until `ready()` (e.g. someone has a bid up)."""
    waited = 0.0
    while not ready() and waited < limit:
        await wait(pilot, clock, 1)
        waited += 1
    assert ready()


async def send(pilot, text: str) -> str:
    """Type a command on the outcry command line; return the newest history line."""
    await pilot.press(*typed(text), "enter")
    await pilot.pause()
    return pilot.app.screen.history[-1].plain


async def test_full_easy_game_with_the_fake_clock(isolated_home):
    app = build_app(parse_args(["outcry", "--seed", "7"]))
    clock = FakeClock()
    app.outcry_clock = clock
    seen = {"opened": 0, "auto": 0, "responded": 0, "buy": 0, "sell": 0, "invalid": 0}
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen) and app.screen.ui.source.key == "outcry"
        await pilot.press("enter")  # EASY
        await pilot.pause()
        game = app.screen.game
        assert game.seed == 7 and game.mode == "EASY"
        assert game.setup.openers.count(YOU) >= 1

        while not isinstance(app.screen, FinalScreen):
            screen = app.screen
            n = game.round.number
            if isinstance(screen, OpenScreen) and game.phase == "open":
                if seen["opened"] == 0:
                    assert screen.query_one("#in-bid", Input).has_focus
                    fair = round(game.fair(YOU))
                    await pilot.press(*typed(str(fair - 5)), "tab", *typed(str(fair + 5)), "enter")
                    await pilot.pause()
                    assert (game.rounds[n - 1].bid, game.rounds[n - 1].ask) == (fair - 5, fair + 5)
                    seen["opened"] += 1
                else:
                    await wait(pilot, clock, game.config.respond_s)  # let the open timer run out
                    assert game.rounds[n - 1].auto_quoted
                    seen["auto"] += 1
            elif isinstance(screen, OpenScreen):
                await pilot.press("b" if seen["responded"] == 0 else "p")
                await pilot.pause()
                assert any(x.seat == YOU for x in game.rounds[n - 1].responses)
                seen["responded"] += 1
            elif isinstance(screen, TradingScreen):
                assert screen.query_one("#cmd", Input).has_focus
                if n == 1:
                    await wait(pilot, clock, 6)  # let the traders quote
                    assert (await send(pilot, "b 10")).endswith("✓ bid 10 posted")
                    assert (await send(pilot, "b 11")).endswith("✓ bid 11 posted")  # replaces
                    assert game.book.order_of(YOU, BID).price == 11
                    assert (await send(pilot, "o 9999")).endswith("✓ offer 9999 posted")
                    assert (await send(pilot, "xb")).endswith("✓ cancelled your bid")
                    await pilot.press("escape")  # Esc cancels all
                    await pilot.pause()
                    assert game.book.order_of(YOU, OFFER) is None
                    line = await send(pilot, "o banana")
                    assert "✗" in line and "not a price" in line
                    seen["invalid"] += 1
                    await pilot.press("up")  # ↑ recalls the last command
                    assert screen.query_one("#cmd", Input).value == "o banana"
                    await pilot.press(*["backspace"] * 8)
                    pos = game.positions[YOU]
                    await until(pilot, clock, lambda: game.book.best_offer(exclude=YOU))
                    line = await send(pilot, "buy")
                    assert "✓ bought" in line and game.positions[YOU] == pos + 1
                    seen["buy"] += 1
                    await until(pilot, clock, lambda: game.book.best_bid(exclude=YOU))
                    line = await send(pilot, "sell")
                    assert "✓ sold" in line and game.positions[YOU] == pos
                    seen["sell"] += 1
                    assert "lifts" in str(screen.query_one("#tape", Static).content)
                await wait(pilot, clock, game.config.outcry_s)
            elif isinstance(screen, CloseScreen):
                assert len(game.public().reveals) == n
                await pilot.press("enter")
                await pilot.pause()
            else:
                pytest.fail(f"unexpected screen {screen!r}")

        assert seen == {"opened": 1, "auto": 1, "responded": 5, "buy": 1, "sell": 1, "invalid": 1}
        assert len(app.screen.game.public().reveals) == 8
        answer = game.score(YOU)  # the net trade score, not the dollar P&L
        await pilot.press(*typed(str(answer)), "enter")
        await pilot.pause()
        assert isinstance(app.screen, ResultsScreen) and game.report_correct
        res = game.results()
        assert sum(row.pnl for row in res.leaderboard) == 0
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, TapeScreen)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert (isolated_home / "outcry_session_7.csv").exists()

    record = json.loads((isolated_home / "outcry_history.jsonl").read_text().splitlines()[-1])
    assert record["game"] == "outcry" and record["seed"] == 7 and record["reports_correct"] == 1


async def test_report_timeout_is_wrong():
    app = build_app(parse_args(["outcry", "--seed", "7"]))
    clock = FakeClock()
    app.outcry_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        game = app.screen.game
        while not isinstance(app.screen, FinalScreen):
            if isinstance(app.screen, CloseScreen):
                await pilot.press("enter")
                await pilot.pause()
            else:
                await wait(pilot, clock, 60)
        await wait(pilot, clock, game.config.report_s)
        assert isinstance(app.screen, ResultsScreen)
        assert game.reported is None and not game.report_correct
        assert not game.results().report_correct


async def test_home_lists_four_games_and_outcry_lobby():
    app = MTTGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        rows = [str(r) for r in app.screen.query_one("#game-list").rows]
        assert [r.split()[0] for r in rows] == ["CARD", "DICE", "TRADING", "OUTCRY", "ETF"]
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        lobby = app.screen
        assert isinstance(lobby, LobbyScreen) and lobby.ui.source.key == "outcry"
        assert "8 hidden numbers · 1 contract · settles at the sum of all 8" in str(
            lobby.query_one("#subtitle", Static).content)
        assert lobby.menu == ["EASY", "MEDIUM", "HARD", "CUSTOM…", None, "HOW TO PLAY", "COMMANDS", "STATS", "QUIT"]
        labels = list(lobby.query_one("#modes-table", Static).content.columns[0].cells)
        assert "helper panel" in labels and not any("width" in label for label in labels)
        await pilot.press("down", "down", "down", "down", "down", "enter")  # COMMANDS
        await pilot.pause()
        assert isinstance(app.screen, CommandsScreen)
        await pilot.press("escape")
        await pilot.pause()
        for key, cls in (("h", HowToScreen), ("c", CustomScreen)):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, cls)
            if cls is CustomScreen:
                assert not app.screen.query_one("#events-list").parent.display  # Outcry has no market events
                await pilot.press("tab", "space", "enter")  # nothing to toggle: no crash
                await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()


async def test_invalid_open_is_rejected_inline():
    app = build_app(parse_args(["outcry", "--seed", "7"]))
    clock = FakeClock()
    app.outcry_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        game = app.screen.game
        while not (isinstance(app.screen, OpenScreen) and game.phase == "open"):
            if isinstance(app.screen, CloseScreen):
                await pilot.press("enter")
                await pilot.pause()
            elif isinstance(app.screen, OpenScreen):
                await pilot.press("p")
                await pilot.pause()
            else:
                await wait(pilot, clock, 60)
        await pilot.press(*typed("430"), "tab", *typed("400"), "enter")  # ask below bid
        await pilot.pause()
        assert isinstance(app.screen, OpenScreen) and game.phase == "open"
        assert "ask must be above bid" in str(app.screen.query_one("#open-error", Static).content)
        assert str(app.screen.query_one("#width-line", Static).content) == "width -30"  # width only, no ✓/✗


async def test_real_clock_drives_the_game_by_default():
    """Without an injected clock the screens feed real (monotonic) time into the tick clock."""
    app = build_app(parse_args(["outcry", "--seed", "7"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        game = app.screen.game
        start, left = game.now, game.seconds_left()
        await pilot.pause(0.8)
        assert game.now - start >= 2 and game.seconds_left() < left
