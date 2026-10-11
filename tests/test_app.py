"""Textual Pilot smoke tests: drive the real app through a full EASY session."""

import json
from decimal import Decimal

import pytest

from textual.widgets import Static

from met_games.__main__ import build_app, parse_args
from met_games.app import HomeScreen, METGamesApp
from met_games.games.card.config import EASY
from met_games.games.sumgame.screens.common import start_session
from met_games.games.sumgame.screens.custom import CustomScreen
from met_games.games.sumgame.screens.lobby import LobbyScreen
from met_games.games.sumgame.screens.recap import RecapScreen
from met_games.games.sumgame.screens.reveal import RevealScreen
from met_games.games.sumgame.screens.round import RoundScreen
from met_games.widgets import TopBar

SIZE = (150, 50)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def key_names(value: int) -> list[str]:
    return ["minus" if ch == "-" else ch for ch in str(value)]


async def test_easy_session_reaches_recap(isolated_home):
    app = METGamesApp(seed=42)
    async with app.run_test(size=SIZE) as pilot:
        assert isinstance(app.screen, HomeScreen)
        await pilot.press("enter")
        assert isinstance(app.screen, LobbyScreen)
        await pilot.press("enter")  # EASY is preselected
        await pilot.pause()

        for i, action in enumerate(["b", "p", "s", "p"]):
            assert isinstance(app.screen, RoundScreen)
            session = app.screen.session
            assert session.seed == 42 and session.mode == "EASY"
            await pilot.press(action)
            await pilot.pause()

            assert isinstance(app.screen, RevealScreen)
            rnd = session.rounds[-1]
            assert rnd.decision.action == {"b": "buy", "p": "pass", "s": "sell"}[action]
            answer = rnd.pnl if i != 2 else rnd.pnl + 1  # one deliberately wrong report
            await pilot.press(*key_names(answer), "enter")
            await pilot.pause()
            assert rnd.reported == answer
            assert rnd.report_correct is (i != 2)
            await pilot.press("enter")
            await pilot.pause()

        assert isinstance(app.screen, RecapScreen)
        assert len(session.rounds) == 4

    lines = (isolated_home / "card_history.jsonl").read_text().splitlines()
    record = json.loads(lines[-1])
    assert record["mode"] == "EASY" and record["seed"] == 42
    assert record["reports_correct"] == 3 and record["reports_total"] == 4


async def play_cli_session(argv):
    """Launch via the CLI args, pass every round, report correctly; return each round's deal + quotes."""
    app = build_app(parse_args(argv))
    trace = []
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen)  # `card` skips the home screen
        await pilot.press("enter")
        await pilot.pause()
        while isinstance(app.screen, RoundScreen):
            rnd = app.screen.rnd
            trace.append(([str(c) for c in rnd.cards], list(rnd.face_up), rnd.event, list(rnd.tape)))
            await pilot.press("p")
            await pilot.pause()
            await pilot.press(*key_names(rnd.pnl), "enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
        assert isinstance(app.screen, RecapScreen)
        assert app.screen.query_one(TopBar).round_text == "RECAP · SEED 99"
        assert app.screen.session.seed == 99
    return trace


async def test_cli_same_seed_same_deals_and_quotes():
    a = await play_cli_session(["card", "--seed", "99"])
    b = await play_cli_session(["card", "--seed", "99"])
    assert len(a) == 4 and a == b


def test_cli_args_and_help(capsys):
    args = parse_args(["card", "--seed", "12"])
    assert (args.game, args.seed) == ("card", 12)
    assert (parse_args([]).game, parse_args([]).seed) == (None, None)
    with pytest.raises(SystemExit):
        parse_args(["--help"])
    out = capsys.readouterr().out
    assert "--seed INT" in out and "card" in out and "skipping the home screen" in out
    with pytest.raises(SystemExit):
        parse_args(["--seed", "abc"])


async def test_recap_shows_out_of_risk_reason():
    app = METGamesApp(seed=5)
    async with app.run_test(size=SIZE) as pilot:
        start_session(app, EASY.replace(budget=1), "CUSTOM", switch=False)
        await pilot.pause()
        assert isinstance(app.screen, RecapScreen)
        banner = str(app.screen.query_one("#end-reason", Static).content)
        assert "out of risk capacity" in banner


async def test_other_screens_open_and_close():
    app = METGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        for key in ("h", "c"):
            await pilot.press(key)
            await pilot.pause()
            assert not isinstance(app.screen, LobbyScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, LobbyScreen)
        await pilot.press("down", "down", "down", "down", "down", "enter")  # STATS
        await pilot.pause()
        await pilot.press("escape")
        assert isinstance(app.screen, LobbyScreen)


async def test_custom_screen_edits_and_validates():
    app = METGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter", "c")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, CustomScreen)
        await pilot.press("down", "down", "down", "right", "right", "right")  # face up max 1 → 4 > cards min 3
        assert screen.config.face_up_max == 4
        assert screen.config.errors()
        await pilot.press("enter")  # refuses to start
        await pilot.pause()
        assert isinstance(app.screen, CustomScreen)
        await pilot.press("left", "left", "left")
        assert not screen.config.errors()


# ── Dice Game ───────────────────────────────────────────────────────────────

DICE_KEYS = {"-": "minus", ".": "full_stop"}


def typed(text: str) -> list[str]:
    return [DICE_KEYS.get(ch, ch) for ch in text]


async def test_home_lists_both_games():
    app = METGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        rows = [str(r) for r in app.screen.query_one("#game-list").rows]
        assert any("CARD GAME" in r for r in rows) and any("DICE GAME" in r for r in rows)
        await pilot.press("down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen) and app.screen.ui.source.key == "dice"


async def test_dice_easy_session_via_cli_reaches_recap(isolated_home):
    app = build_app(parse_args(["dice", "--seed", "7"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen) and app.screen.ui.source.key == "dice"
        await pilot.press("enter")  # EASY
        await pilot.pause()
        decimal_reports = 0
        for i, action in enumerate(["b", "p", "s", "p"]):
            assert isinstance(app.screen, RoundScreen)
            session = app.screen.session
            assert app.screen.query_one("#market").border_title == "MARKET · TICK 0.25"
            await pilot.press(action)
            await pilot.pause()
            assert isinstance(app.screen, RevealScreen)
            rnd = session.rounds[-1]
            # round 1 as "-3.50", round 3 trailing zeros stripped ("-3.5"), passes as plain "0"
            text = f"{rnd.pnl:.2f}" if i == 0 else format(rnd.pnl.normalize(), "f") if i == 2 else str(rnd.pnl)
            decimal_reports += "." in text
            await pilot.press(*typed(text), "enter")
            await pilot.pause()
            assert rnd.report_correct is True, (text, rnd.pnl)
            await pilot.press("enter")
            await pilot.pause()
        assert decimal_reports >= 1
        assert isinstance(app.screen, RecapScreen)
        assert app.screen.query_one(TopBar).round_text == "RECAP · SEED 7"
        assert session.seed == 7 and len(session.rounds) == 4

    record = json.loads((isolated_home / "dice_history.jsonl").read_text().splitlines()[-1])
    assert record["game"] == "dice" and record["seed"] == 7 and record["reports_correct"] == 4


async def test_dice_wrong_decimal_report_is_marked_wrong():
    app = build_app(parse_args(["dice", "--seed", "7"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("b")
        await pilot.pause()
        rnd = app.screen.session.rounds[-1]
        await pilot.press(*typed(f"{rnd.pnl + Decimal('0.25'):.2f}"), "enter")
        await pilot.pause()
        assert rnd.report_correct is False


async def test_card_market_title_unchanged():
    app = build_app(parse_args(["card", "--seed", "3"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.query_one("#market").border_title == "MARKET"
