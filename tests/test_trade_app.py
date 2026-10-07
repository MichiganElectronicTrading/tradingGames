"""Textual Pilot tests for the Trading Game: a full EASY session from the CLI, plus HARD screens."""

import json
import math

import pytest
from textual.widgets import Input, Static

from mtt_games.__main__ import build_app, parse_args
from mtt_games.app import MTTGamesApp
from mtt_games.games.sumgame.screens.custom import CustomScreen
from mtt_games.games.sumgame.screens.howto import HowToScreen
from mtt_games.games.sumgame.screens.lobby import LobbyScreen
from mtt_games.games.trade.engine import TRADERS, YOU
from mtt_games.games.trade.screens.recap import RecapScreen
from mtt_games.games.trade.screens.settle import SettleScreen
from mtt_games.games.trade.screens.turns import FillsScreen, MakeScreen, TakeScreen
from mtt_games.widgets import TopBar

SIZE = (150, 50)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTT_GAMES_HOME", str(tmp_path))
    return tmp_path


def keys(value: int) -> list[str]:
    return ["minus" if ch == "-" else ch for ch in str(value)]


def filling_quote(session) -> tuple[int, int]:
    """A quote every trader wants to buy: ask = ⌊lowest est⌋ − 1, so est ≥ ask + 1 for all of them."""
    hand = session.current
    ask = math.floor(min(hand.est(t) for t in TRADERS)) - 1
    bid = ask - session.config.width_min
    assert session.quote_errors(bid, ask, session.config.FIXED_SIZE) == []
    return bid, ask


async def make_market(pilot, bid: int, ask: int) -> None:
    screen = pilot.app.screen
    assert isinstance(screen, MakeScreen)
    assert screen.query_one("#in-bid", Input).has_focus
    await pilot.press(*keys(bid), "tab", *keys(ask), "enter")
    await pilot.pause()


async def test_easy_session_via_cli_reaches_recap(isolated_home):
    app = build_app(parse_args(["trade", "--seed", "7"]))
    made_and_filled = takes = passes = wrong = 0
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen) and app.screen.ui.source.key == "trade"
        await pilot.press("enter")  # EASY
        await pilot.pause()
        session = app.screen.session
        assert session.seed == 7 and session.mode == "EASY"

        while not isinstance(app.screen, RecapScreen):
            screen = app.screen
            hand = session.current
            bar = app.screen.query_one(TopBar)
            assert bar.crumb == "TRADING GAME ▸ EASY" and bar.round_text == f"HAND {hand.number} / 4"
            if isinstance(screen, MakeScreen):
                await make_market(pilot, *filling_quote(session))
                turn = hand.turn
                assert turn.posted and turn.done and turn.fills
                made_and_filled += 1
                assert isinstance(app.screen, FillsScreen)
                await pilot.press("enter")  # skip the feed
                await pilot.pause()
                assert "round trips" in str(app.screen.query_one("#feed-footer", Static).content)
                await pilot.press("enter")
                await pilot.pause()
            elif isinstance(screen, TakeScreen):
                turn = hand.turn
                max_buy, max_sell = session.take_limits()
                if takes == 0 and (max_buy or max_sell):
                    await pilot.press("b" if max_buy else "s")
                    takes += 1
                    assert turn.actions[0].who == YOU and turn.actions[0].is_fill
                else:
                    await pilot.press("p")
                    passes += 1
                await pilot.pause()
                assert turn.done and turn.actions[0].who == YOU  # you acted first
                assert "you act first" not in str(screen.query_one("#markets", Static).content)
                await pilot.press("enter")
                await pilot.pause()
            elif isinstance(screen, SettleScreen):
                assert hand.settled and sum(hand.pnls().values()) == 0
                answer = hand.pnl(YOU) + (1 if hand.number == 2 else 0)  # one deliberately wrong report
                await pilot.press(*keys(answer), "enter")
                await pilot.pause()
                assert hand.reported == answer and hand.report_correct is (hand.number != 2)
                wrong += hand.number == 2
                await pilot.press("w")
                await pilot.pause()
                assert screen.query_one("#walk-panel").display
                await pilot.press("enter")
                await pilot.pause()
            else:
                pytest.fail(f"unexpected screen {screen!r}")

        assert made_and_filled == 4 and takes == 1 and passes == 11 and wrong == 1
        assert len(session.hands) == 4 and session.finished
        assert app.screen.query_one(TopBar).round_text == "RECAP · SEED 7"

    record = json.loads((isolated_home / "trade_history.jsonl").read_text().splitlines()[-1])
    assert record["game"] == "trade" and record["seed"] == 7 and record["mode"] == "EASY"
    assert record["reports_correct"] == 3 and record["reports_total"] == 4


async def test_home_lists_all_three_games():
    app = MTTGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        rows = [str(r) for r in app.screen.query_one("#game-list").rows]
        assert [r.split()[0] for r in rows] == ["CARD", "DICE", "TRADING"]
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen) and app.screen.ui.source.key == "trade"
        labels = list(app.screen.query_one("#modes-table", Static).content.columns[0].cells)
        assert "your allowed width" in labels and "learn_rate" in labels and "peeks" in labels
        for key, cls in (("h", HowToScreen), ("c", CustomScreen)):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, cls)
            await pilot.press("escape")
            await pilot.pause()


async def test_hard_shows_event_banner_and_flips():
    app = build_app(parse_args(["trade", "--seed", "3"]))
    flips = 0
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("down", "down", "enter")  # HARD
        await pilot.pause()
        session = app.screen.session
        assert session.mode == "HARD"
        while session.current.number == 1:
            screen = app.screen
            hand = session.current
            if isinstance(screen, SettleScreen):
                break
            assert screen.query_one(".event-banner", Static)  # an event every hand on Hard
            if hand.turn.flipped is not None:
                flips += 1
                line = str(screen.query_one(".flip-line", Static).content)
                assert line == f"▲ {hand.items[hand.turn.flipped]} turned face up"
            if isinstance(screen, MakeScreen):
                m = hand.public()
                bid = round(m.fair) - 1
                await make_market(pilot, bid, bid + 2)
                await pilot.press("enter", "enter")
            else:
                await pilot.press("p", "enter")
            await pilot.pause()
        assert flips == sum(f is not None for f in session.current.flips) > 0


async def test_invalid_quote_is_rejected_with_a_message():
    app = build_app(parse_args(["trade", "--seed", "7"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        session = app.screen.session
        while not isinstance(app.screen, MakeScreen):  # pass until it's your market
            await pilot.press("p", "enter")
            await pilot.pause()
        await make_market(pilot, 20, 21)  # width 1 < Easy's 2
        assert isinstance(app.screen, MakeScreen) and not session.current.turn.posted
        assert "width 1 is outside the allowed 2–6" in str(app.screen.query_one("#quote-error", Static).content)
        assert session.current.turn.maker == YOU and not session.current.turn.done  # still your turn
