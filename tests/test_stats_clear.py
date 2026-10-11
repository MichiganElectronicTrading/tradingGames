"""Stats screen: the CLEAR STATS button asks first, then deletes only that game's history."""

import pytest
from rich.table import Table

from met_games import storage
from met_games.__main__ import build_app, parse_args
from met_games.games.sumgame.screens.stats import ConfirmClearScreen, StatsScreen
from met_games.widgets import KeyButton

RECORD = {"mode": "EASY", "final_balance": 512, "edge_taken": 1.5, "reports_correct": 3, "reports_total": 4}
SIZE = (150, 50)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))


async def go_to_stats(pilot) -> None:
    await pilot.press("down", "down", "down", "down", "down", "enter")  # lobby menu → STATS
    await pilot.pause()
    assert isinstance(pilot.app.screen, StatsScreen)


async def test_clear_stats_confirms_then_clears_only_this_game():
    storage.append_jsonl("dice_history.jsonl", RECORD)
    storage.append_jsonl("card_history.jsonl", RECORD)
    app = build_app(parse_args(["dice"]))
    async with app.run_test(size=SIZE) as pilot:
        await go_to_stats(pilot)
        table = app.screen.query_one("#stats-table")
        assert isinstance(table.content, Table)
        assert not app.screen.query_one("#clear", KeyButton).disabled

        await pilot.press("c")  # asks first…
        await pilot.pause()
        assert isinstance(app.screen, ConfirmClearScreen)
        await pilot.press("n")  # …and cancelling deletes nothing
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen)
        assert storage.read_jsonl("dice_history.jsonl") == [RECORD]

        await pilot.click("#clear")  # the button opens the same prompt
        await pilot.pause()
        assert isinstance(app.screen, ConfirmClearScreen)
        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen)
        assert storage.read_jsonl("dice_history.jsonl") == []
        assert storage.read_jsonl("card_history.jsonl") == [RECORD]  # the other game is untouched
        assert "no sessions yet" in table.content.plain
        assert app.screen.query_one("#clear", KeyButton).disabled


async def test_clear_with_no_history_does_not_prompt():
    app = build_app(parse_args(["card"]))
    async with app.run_test(size=SIZE) as pilot:
        await go_to_stats(pilot)
        assert app.screen.query_one("#clear", KeyButton).disabled
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen)
