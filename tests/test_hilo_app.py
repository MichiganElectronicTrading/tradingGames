"""Hi-Lo Pilot tests on a fake clock (`app.hilo_clock`): nothing waits on real time."""

import json

import pytest
from textual.geometry import Region
from textual.widgets import Static

from met_games.__main__ import build_app, parse_args
from met_games.app import METGamesApp
from met_games.games.hilo.config import EASY, FULL, INTERVIEW, REDBLACK
from met_games.games.hilo.engine import HiloGame
from met_games.games.hilo.model import (
    DISCIPLINE,
    FAST,
    HIGHER,
    LIGHTNING,
    LOWER,
    MISS,
    NORMAL,
    PERFECT,
    RED,
    SAT_OUT,
    pct,
)
from met_games.games.hilo.scores import SCORES_FILE
from met_games.games.hilo.screens.bet import BetScreen
from met_games.games.hilo.screens.end import EndScreen, HighScoresScreen, ReviewScreen
from met_games.games.hilo.screens.lobby import HiloLobby
from met_games.games.hilo.screens import screen_for
from met_games.games.hilo.ui import SCORING_NOTE_UNTIMED, scoring_rows

SIZE = (150, 50)
SIDE_KEY = {HIGHER: "h", LOWER: "l", RED: "r", "BLACK": "b"}


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


async def wait(pilot, clock, seconds):
    clock.t += seconds
    pilot.app.screen.sync()
    await pilot.pause()


async def kelly_bet(pilot, game):
    """Stake first (tens), then the side, then ⏎ — so quick lock doesn't fire early."""
    o = game.odds()
    if o.right is None:
        await pilot.press("0", "enter")
    else:
        await pilot.press(str(min(9, round(pct(o.k) / 10))) if pct(o.k) < 95 else "a", SIDE_KEY[o.right], "enter")
    await pilot.pause()


async def skip_flash(pilot):
    await pilot.press("enter")
    await pilot.pause()


async def test_full_interview_easy_game_untimed(isolated_home):
    app = build_app(parse_args(["hilo", "--seed", "7"]))
    clock = FakeClock()
    app.hilo_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        assert isinstance(lobby, HiloLobby) and lobby.deck == INTERVIEW
        await pilot.press("enter")  # EASY · Interview
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BetScreen)
        g = screen.game
        assert g.seed == 7 and g.mode == "EASY" and g.total_bets == 12 and not g.config.timed
        # no clock: the STAKE GUIDE (key map + combo) stands in for it
        assert not screen.query("#clock") and "COMBO ×1" in str(screen.query_one("#guide", Static).content)

        # 1 · LOWER 85% at once (k = 83%): PERFECT, no speed multiplier — 100 × combo ×1
        await pilot.press("8", "right", "l", "enter")
        await pilot.pause()
        b = g.bets[-1]
        assert (b.side, b.percent, b.grade, b.tier, b.points) == (LOWER, 85, PERFECT, NORMAL, 100)
        assert app.screen.query_one("#flash-panel").display  # the reveal flash is up
        assert "LIGHTNING" not in str(app.screen.query_one("#flash", Static).content)
        await wait(pilot, clock, 0.7)  # …and ends on its own after 0.6 s
        assert g.phase == "bet" and g.number == 2 and not app.screen.query_one("#flash-panel").display

        # 2 · quick lock: H then 1 locks HIGHER 10% (k = 9%) — 100 × combo ×1.1
        await pilot.press("h", "1")
        await pilot.pause()
        b = g.bets[-1]
        assert (b.side, b.percent, b.grade, b.points) == (HIGHER, 10, PERFECT, 110)
        await skip_flash(pilot)

        # 3 · a minute passes: no timeout. Shift+arrows and [ ] snap the stake to 25s and never lock
        await wait(pilot, clock, 60)
        assert g.phase == "bet" and g.number == 3 and len(g.bets) == 2
        assert "COMBO ×1.2 · streak 2" in str(app.screen.query_one("#guide", Static).content)
        await pilot.press("h", "shift+right", "shift+right")
        await pilot.pause()
        assert app.screen.percent == 50 and len(g.bets) == 2
        await pilot.press("left_square_bracket", "left")
        assert app.screen.percent == 20
        await pilot.press("right_square_bracket", "right_square_bracket", "shift+left")
        assert app.screen.percent == 25 and len(g.bets) == 2  # 20 → 25 → 50 → 25
        await pilot.press("0")  # a stake key quick-locks: sit out
        await pilot.pause()
        assert g.bets[-1].grade in (SAT_OUT, DISCIPLINE) and not g.bets[-1].timeout
        await skip_flash(pilot)

        # 4 · MISS: HIGHER on a LOWER spot (J showing, k = 78% LOWER)
        await pilot.press("h", "5")
        await pilot.pause()
        assert (g.bets[-1].side, g.bets[-1].grade) == (HIGHER, MISS)
        await skip_flash(pilot)

        while g.number < 9:
            await kelly_bet(pilot, g)
            await skip_flash(pilot)
        # 9 · no edge (7 showing, 2 higher / 2 lower): sitting out is DISCIPLINE
        assert g.odds().k == 0
        await pilot.press("0", "enter")
        await pilot.pause()
        assert g.bets[-1].grade == DISCIPLINE
        await skip_flash(pilot)

        while not isinstance(app.screen, EndScreen):
            await kelly_bet(pilot, g)
            await skip_flash(pilot)
        end = app.screen
        assert len(g.bets) == 12 and not g.bust and not any(b.timeout for b in g.bets)
        assert str(end.query_one("#new-high", Static).content) == "★ NEW HIGH SCORE ★"
        assert "LIGHTNING" not in str(end.query_one("#end-left").query(Static).last().content)
        await pilot.press("b")
        await pilot.pause()
        assert isinstance(app.screen, ReviewScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, EndScreen)

    saved = json.loads((isolated_home / SCORES_FILE).read_text())
    entry = saved["interview/EASY/untimed"][0]
    assert (entry["score"], entry["seed"], entry["timed"]) == (g.score, 7, False)


async def test_timed_bets_bring_back_the_clock():
    app = build_app(parse_args(["hilo"]))
    clock = FakeClock()
    app.hilo_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(screen_for(HiloGame(EASY.replace(timed=True, seed=7), "CUSTOM")))
        await pilot.pause()
        screen = app.screen
        g = screen.game
        assert screen.query_one("#clock") and not screen.query("#guide")
        await pilot.press("8", "right", "l", "enter")  # at once: LIGHTNING ×2
        await pilot.pause()
        assert (g.bets[-1].tier, g.bets[-1].points) == (LIGHTNING, 200)
        await skip_flash(pilot)
        await wait(pilot, clock, g.config.time_s)
        assert g.bets[-1].timeout and g.bets[-1].grade == MISS


async def test_hard_full_deck_hides_the_counts():
    app = build_app(parse_args(["hilo", "--seed", "3"]))
    clock = FakeClock()
    app.hilo_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("down", "down")
        await pilot.pause()
        assert app.screen.deck == FULL  # HARD defaults to the full deck
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BetScreen) and screen.game.mode == "HARD" and screen.game.total_bets == 51
        board = str(screen.query_one("#board", Static).content)
        assert "cards left 51" in board and "lower" not in board and "P higher" not in board
        await kelly_bet(pilot, screen.game)
        assert len(screen.game.bets) == 1


async def test_red_black_bet():
    app = build_app(parse_args(["hilo", "--seed", "5"]))
    clock = FakeClock()
    app.hilo_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("down", "down", "down", "enter")  # RED/BLACK
        await pilot.pause()
        screen = app.screen
        g = screen.game
        assert isinstance(screen, BetScreen) and g.config.deck == REDBLACK and g.total_bets == 52
        assert "?" in str(screen.query_one("#card", Static).content)  # face down
        await pilot.press("r", "3")  # quick lock: RED 30%
        await pilot.pause()
        assert (g.bets[-1].side, g.bets[-1].percent) == (RED, 30)


async def test_home_lists_six_games_and_the_lobby_deck_picker():
    app = METGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        rows = [str(r) for r in app.screen.query_one("#game-list").rows]
        assert [r.split()[0] for r in rows] == ["CARD", "DICE", "TRADING", "OUTCRY", "ETF", "HI/LO", "MATH"]
        await pilot.press("down", "down", "down", "down", "down", "enter")
        await pilot.pause()
        lobby = app.screen
        assert isinstance(lobby, HiloLobby) and lobby.deck == INTERVIEW
        await pilot.press("d")
        assert lobby.deck == FULL and lobby.picked
        await pilot.press("down")  # MEDIUM keeps the picked deck
        assert lobby.deck == FULL
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, HighScoresScreen)
        await pilot.press("right", "escape")
        await pilot.pause()
        for key in ("h", "c"):
            await pilot.press(key)
            await pilot.pause()
            assert not isinstance(app.screen, HiloLobby)
            await pilot.press("escape")
            await pilot.pause()


async def test_deck_flag_starts_on_that_deck():
    app = build_app(parse_args(["hilo", "--deck", "redblack"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert app.screen.deck == REDBLACK


async def test_lobby_scoring_panel_is_a_table_that_fits_at_120x40():
    app = build_app(parse_args(["hilo"]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        table = app.screen.query_one("#scoring-table", Static)
        lines = [strip.text.rstrip() for strip in table.render_lines(Region(0, 0, *table.size))]
        shown = scoring_rows(timed=False)
        rows = [r for r in shown if r]
        assert len(rows) == 9 and len(shown) == 10  # untimed: no LIGHTNING / FAST rows; 9 rules + the divider
        # one line per rule + the divider + the footnote: nothing wrapped onto a second line
        assert len(lines) == len(shown) + 1 and lines[-1] == SCORING_NOTE_UNTIMED
        assert not any(line.startswith(("LIGHTNING", "FAST")) for line in lines)
        for name, _, desc, value, _ in rows:
            assert sum(1 for line in lines[:-1] if line.startswith(name + " ")) == 1, name
            line = next(line for line in lines if line.startswith(name + " "))
            assert desc in line and line.endswith(value)  # description and value on the same line, uncut
        assert "…" not in "".join(lines)
        panel = app.screen.query_one("#scoring")
        assert panel.region.bottom <= app.screen.query_one("KeyBar").region.y  # fully on screen


async def test_square_brackets_match_shift_arrows():
    actions = {b.key: b.action for b in BetScreen.BINDINGS}
    assert actions["left_square_bracket"] == actions["shift+left"] == "snap(-1)"
    assert actions["right_square_bracket"] == actions["shift+right"] == "snap(1)"
    app = build_app(parse_args(["hilo", "--seed", "7"]))
    app.hilo_clock = FakeClock()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        for start in (0, 13, 25, 60, 100):
            got = []
            for keys in (("shift+right",), ("right_square_bracket",), ("shift+left",), ("left_square_bracket",)):
                screen.percent = start
                await pilot.press(*keys)
                got.append(screen.percent)
            assert got[0] == got[1] and got[2] == got[3], start
        assert screen.game.bets == []  # arrows never lock


@pytest.mark.parametrize("deck,up,down", [("interview", HIGHER, LOWER), ("full", HIGHER, LOWER), ("redblack", RED, "BLACK")])
async def test_up_and_down_arrows_pick_the_side(deck, up, down):
    app = build_app(parse_args(["hilo", "--seed", "7", "--deck", deck]))
    app.hilo_clock = FakeClock()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, BetScreen) and screen.game.config.deck == deck
        await pilot.press("up")
        assert screen.side == up
        await pilot.press("down")
        assert screen.side == down
        await pilot.press("up", "3")  # quick lock still fires on the stake key
        await pilot.pause()
        assert (screen.game.bets[-1].side, screen.game.bets[-1].percent) == (up, 30)
