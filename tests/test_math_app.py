"""Mental Math Pilot tests on a fake clock (`app.math_clock`): nothing waits on real time."""

import pytest
from textual.widgets import Static

from met_games.__main__ import build_app, parse_args
from met_games.app import METGamesApp
from met_games.games.math import daily
from met_games.games.math.config import DAILY, DRILL, OPTIVER, SPRINT, SURVIVAL
from met_games.games.math.history import load_bests, load_history, load_runs
from met_games.games.math.screens.custom import MathCustomScreen
from met_games.games.math.screens.daily import DailyScreen
from met_games.games.math.screens.lobby import MathLobby
from met_games.games.math.screens.play import OptiverScreen, RunScreen
from met_games.games.math.screens.report import ReportScreen, TipsScreen
from met_games.games.math.screens.stats import StatsScreen
from met_games.widgets import TopBar

SIZE = (150, 50)


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def make_app(*argv):
    app = build_app(parse_args(list(argv)))
    clock = FakeClock()
    app.math_clock = clock
    return app, clock


async def answer(pilot, clock, seconds=2.0):
    clock.t += seconds
    await pilot.press(*pilot.app.screen.run.problem.answer_text)
    await pilot.pause()


async def wait(pilot, clock, seconds):
    clock.t += seconds
    pilot.app.screen.sync()
    await pilot.pause()


def text_of(screen, selector):
    return str(screen.query_one(selector, Static).render())


async def test_home_lists_seven_games():
    app = METGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        rows = [str(r) for r in app.screen.query_one("#game-list").rows]
        assert [r.split()[0] for r in rows] == ["CARD", "DICE", "TRADING", "OUTCRY", "ETF", "HI/LO", "MATH", "None",
                                                "SETTINGS", "QUIT"]
        await pilot.press(*["down"] * 6, "enter")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)


async def test_full_sprint_with_a_skip():
    app, clock = make_app("math", "--seed", "5")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)
        await pilot.press("enter")  # SPRINT · MEDIUM
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen) and screen.run.mode == SPRINT and screen.run.seed == 5
        for _ in range(3):
            await answer(pilot, clock)
        clock.t += 1
        await pilot.press("tab")
        await pilot.pause()
        await answer(pilot, clock)
        run = screen.run
        assert (run.correct, run.skipped) == (4, 1)
        assert [a.points for a in run.attempts if a.correct] == \
            [round(a.problem.base * (1 + 0.1 * a.streak_before)) for a in run.attempts if a.correct]
        assert run.attempts[3].outcome == "skipped" and run.attempts[4].streak_before == 0  # the skip reset the combo
        assert "CORRECT 4" in text_of(screen, "#strip")
        await wait(pilot, clock, 120)
        report = app.screen
        assert isinstance(report, ReportScreen) and run.over
        assert report.query("#new-best")  # the first run on this board sets the bests
        assert len(load_history()) == 5 and load_runs()[-1]["correct"] == 4
        assert load_bests()["sprint/medium"]["correct"] == 4
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, TipsScreen)
        await pilot.press("escape", "l")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)


async def test_survival_to_game_over():
    app, clock = make_app("math", "--mode", "survival", "--seed", "8")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen) and screen.run.mode == SURVIVAL
        await answer(pilot, clock, 1)
        assert screen.run.time_left_ms == 37_000  # MEDIUM: +8s
        assert "+8s per correct" in text_of(screen, "#clock") and "−0.5s in 4" in text_of(screen, "#clock")
        clock.t += 1
        await pilot.press("tab")
        await pilot.pause()
        assert screen.run.time_left_ms == 31_000
        await wait(pilot, clock, 30.9)
        assert isinstance(app.screen, RunScreen)
        await wait(pilot, clock, 0.2)
        assert isinstance(app.screen, ReportScreen) and screen.run.over and screen.run.time_left_ms == 0
        assert load_runs()[-1]["mode"] == SURVIVAL


async def test_optiver_style_right_wrong_skip():
    app, clock = make_app("math", "--mode", "optiver", "--seed", "3")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, OptiverScreen) and screen.run.mode == OPTIVER
        assert app.screen.query_one(TopBar).round_text == "unofficial practice format"
        run = screen.run
        clock.t += 3
        await pilot.press(str(run.question.correct + 1))
        await pilot.pause()
        clock.t += 4
        await pilot.press(str((run.question.correct + 1) % 4 + 1))
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert (run.correct, run.wrong, run.skipped, run.net, run.i) == (1, 1, 1, 0, 3)
        assert "NET +0" in text_of(screen, "#strip") and "✓ 1" in text_of(screen, "#strip")
        assert "your average" in text_of(screen, "#pace")
        await pilot.press("ctrl+e")  # end run
        await pilot.pause()
        report = app.screen
        assert isinstance(report, ReportScreen) and report.score_title() == "NET"
        assert load_bests() == {}  # a net of 0 isn't a best
        assert [r["outcome"] for r in load_history()] == ["correct", "wrong", "skipped"]


async def test_daily_start_to_card(monkeypatch):
    copied = []
    monkeypatch.setattr(daily, "copy", lambda text: copied.append(text) or True)
    app, clock = make_app("math", "--daily")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, DailyScreen)
        day = app.screen.day
        assert "not played yet" in text_of(app.screen, "#d-correct")
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen) and screen.run.mode == DAILY and daily.started(day)
        assert screen.run.problem == daily.problems(day)[0]
        await answer(pilot, clock)
        await answer(pilot, clock)
        await wait(pilot, clock, 121)
        assert isinstance(app.screen, ReportScreen)
        await pilot.press("c")
        await pilot.pause()
        card = copied[-1].splitlines()
        assert card[0] == f"MET MATH · daily #{daily.number(day)} · sprint M · v1"
        assert card[1].startswith("2 ✓ · ") and card[-1] == "met-games math --daily"
        assert daily.result(day)["correct"] == 2
        await pilot.press("r")  # one attempt: no run again
        await pilot.pause()
        assert isinstance(app.screen, ReportScreen)
        await pilot.press("l", "d")
        await pilot.pause()
        assert isinstance(app.screen, DailyScreen)
        assert text_of(app.screen, "#d-card") == "\n".join(copied[-1].splitlines())
        await pilot.press("enter")  # already played
        await pilot.pause()
        assert isinstance(app.screen, DailyScreen)
        await pilot.press("c")
        assert copied[-1] == copied[0]


async def test_report_drill_then_lobby():
    app, clock = make_app("math", "--mode", "sprint", "--seed", "11")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        first = app.screen.run
        for _ in range(4):
            await answer(pilot, clock)
        await pilot.press("tab")
        await pilot.pause()
        await wait(pilot, clock, 120)
        report = app.screen
        weak = {r.subtype for r in report.report.weak}
        assert len(weak) == 2
        bests = load_bests()
        await pilot.press("d")
        await pilot.pause()
        drill = app.screen
        assert isinstance(drill, RunScreen) and drill.run.mode == DRILL and drill.run.time_left_ms == 120_000
        for _ in range(5):
            await answer(pilot, clock, 1)
        assert {a.problem.subtype for a in drill.run.attempts} <= weak
        await wait(pilot, clock, 120)
        assert isinstance(app.screen, ReportScreen) and not app.screen.query("#new-best")
        assert load_bests() == bests  # drills never count
        assert load_runs()[-1]["mode"] == DRILL and len(load_history()) == len(first.attempts) + 5
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)


async def test_lobby_keys_difficulty_mix_custom_and_stats():
    app, clock = make_app("math")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        await pilot.press("left")
        assert lobby.difficulty == "easy"
        await pilot.press("right", "right", "right")
        assert lobby.difficulty == "custom"
        await pilot.press("1", "2", "3")
        assert lobby.families == ["desk"]
        await pilot.press("4")  # the last one stays on
        assert lobby.families == ["desk"]
        await pilot.press("1")
        assert lobby.families == ["core", "desk"]
        await pilot.press("down", "down", "down")  # SURVIVAL, CHAIN, ESTIMATE
        await pilot.press("down")  # skips the section title to ZETAMAC
        assert lobby.mode == "zetamac"
        await pilot.press("up", "up", "up", "up", "enter")  # SPRINT with CUSTOM → the Custom screen
        await pilot.pause()
        custom = app.screen
        assert isinstance(custom, MathCustomScreen) and custom.duration == 120
        await pilot.press("left", "left")  # duration 1:30
        await pilot.press("enter")
        await pilot.pause()
        run = app.screen.run
        assert run.duration_ms == 90_000 and run.board == "custom"
        assert {a.problem.family for a in (run.skip() for _ in range(12))} == {"core", "desk"}
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert isinstance(app.screen, ReportScreen)
        await pilot.press("l")
        await pilot.pause()
        # SURVIVAL, CHAIN, ESTIMATE, ZETAMAC, OPTIVER-STYLE, FLOW-STYLE, PROBABILITY DRILL, DAILY, MY STATS
        await pilot.press(*["down"] * 9)
        assert lobby.item[1] == "stats"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen)
        stats = app.screen
        assert stats.query_one("#stats-top", TopBar).round_text.startswith("1 run · since ")
        await pilot.press("down", "down")  # MEDIUM → HARD → CUSTOM
        assert stats.difficulty == "custom" and "correct: 0 → 0 → 0" in text_of(stats, "#spark")


async def test_cli_mode_and_difficulty_start_the_run():
    app, clock = make_app("math", "--mode", "sprint", "--difficulty", "hard", "--seed", "2")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        run = app.screen.run
        assert run.board == "hard" and run.seed == 2 and run.problem.level == "hard"
    app, clock = make_app("math", "--mode", "zetamac")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        run = app.screen.run
        assert run.mode == "zetamac" and not run.scored and run.problem.level == "zetamac"
        await answer(pilot, clock)
        assert run.correct == 1 and run.points == 0 and "raw score" in text_of(app.screen, "#strip")
        await wait(pilot, clock, 120)
        assert isinstance(app.screen, ReportScreen) and app.screen.score_title() == "RAW SCORE"
        assert load_bests() == {"zetamac/standard": {"raw": 1, "raw_date": load_runs()[-1]["date"]}}


async def test_custom_survival_edits_the_bonus():
    app, clock = make_app("math")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("right", "right", "down", "enter")  # CUSTOM · SURVIVAL
        await pilot.pause()
        custom = app.screen
        assert isinstance(custom, MathCustomScreen) and custom.rows[0] == "bonus" and "floor" not in custom.rows
        assert custom.bonus_ms == 8_000
        assert "bonus per correct" in text_of(custom, "#custom") and "+8s" in text_of(custom, "#custom")
        await pilot.press("right")  # bonus +9s
        await pilot.press("enter")
        await pilot.pause()
        run = app.screen.run
        assert run.survival and (run.bonus_ms, run.bonus_floor_ms) == (9_000, 1_000)
        await answer(pilot, clock, 1)
        assert run.time_left_ms == 38_000
