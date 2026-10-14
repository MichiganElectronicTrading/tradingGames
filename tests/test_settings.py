"""The settings store (~/.met_games/settings.json): defaults, save and load, a corrupt file, MET_GAMES_HOME, unknown
keys kept; and the Settings screen from the home menu and the math lobby."""

import io
import json

import pytest
from rich.console import Console
from textual.widgets import Static

from met_games import settings
from met_games.__main__ import build_app, parse_args
from met_games.app import METGamesApp
from met_games.games.math.screens.lobby import MathLobby
from met_games.settings_screen import SettingsScreen


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def test_defaults_when_nothing_is_saved(isolated_home):
    assert settings.get("math", "problem_size", "normal") == "normal"
    assert not (isolated_home / "settings.json").exists()


def test_save_and_load_namespaced_per_game(isolated_home):
    settings.set("math", "problem_size", "huge")
    settings.set("math", "answer_size", "large")
    assert settings.get("math", "problem_size", "normal") == "huge"
    assert json.loads((isolated_home / "settings.json").read_text()) == \
        {"math": {"problem_size": "huge", "answer_size": "large"}}


@pytest.mark.parametrize("junk", ["{not json", "[1, 2]", "\xff\xfe", '{"math": "huge"}', ""])
def test_a_corrupt_file_reads_as_defaults_and_is_rewritten(isolated_home, junk):
    (isolated_home / "settings.json").write_bytes(junk.encode("latin-1"))
    assert settings.get("math", "problem_size", "normal") == "normal"
    settings.set("math", "problem_size", "large")
    assert json.loads((isolated_home / "settings.json").read_text())["math"] == {"problem_size": "large"}


def test_met_games_home_is_respected(tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    monkeypatch.setenv("MET_GAMES_HOME", str(other))
    settings.set("math", "answer_size", "huge")
    assert (other / "settings.json").exists()


def test_unknown_keys_survive(isolated_home):
    (isolated_home / "settings.json").write_text(json.dumps(
        {"hilo": {"deck": "full"}, "math": {"theme": "dark", "problem_size": "large"}, "version": 3}))
    settings.set("math", "problem_size", "huge")
    data = json.loads((isolated_home / "settings.json").read_text())
    assert data == {"hilo": {"deck": "full"}, "math": {"theme": "dark", "problem_size": "huge"}, "version": 3}


def plain(renderable, width=140):
    console = Console(width=width, file=io.StringIO(), record=True)
    console.print(renderable)
    return console.export_text()


def text_of(screen, selector):
    return str(screen.query_one(selector, Static).render())


async def test_settings_from_the_home_menu_and_back():
    app = METGamesApp()
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        rows = app.screen.query_one("#game-list").rows
        assert str(rows[-2]).startswith("SETTINGS") and str(rows[-1]) == "QUIT" and rows[-3] is None
        await pilot.press(*["down"] * 7, "enter")  # past the seven games and the divider
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SettingsScreen)
        listing = text_of(screen, "#settings-list")
        assert "MENTAL MATH · DISPLAY" in listing and "PROBLEM SIZE" in listing and "ANSWER SIZE" in listing
        assert "answer size covers what you type and the Optiver-style choices" in listing
        side = " ".join(str(s.render()) for s in screen.query("#settings-side Static"))
        assert "LARGE   3 rows · line digits" in side and "HUGE    5 rows · block digits" in side
        assert "word problems stay plain text" in side and "⌘ + zooms the whole terminal" in side
        preview = plain(screen.query_one("#settings-preview", Static).content)
        assert "7/8 − 0.3125  =" in preview and "0.5625" in preview and "0.625" in preview  # all NORMAL
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.query("#game-list")


async def test_settings_from_the_math_lobby_with_the_comma_key_and_the_menu():
    app = build_app(parse_args(["math"]))
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("comma")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is lobby
        await pilot.press(*["down"] * 10)  # … DAILY, MY STATS, SETTINGS
        assert lobby.item[1] == "settings" and "Display size" in text_of(lobby, "#rules")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is lobby and isinstance(lobby, MathLobby)
