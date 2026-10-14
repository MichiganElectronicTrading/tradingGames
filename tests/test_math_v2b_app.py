"""Mental Math v2b Pilot tests on a fake clock: every lobby entry live, a full Flow-style run to its report (no
feedback mid-run, the clock running through the pause menu, the 6:00 cutoff), and the Probability drill's feedback
with a known mistake's WHY, its report, the adaptive prob level, and MY STATS."""

import pytest
from textual.widgets import Static

from met_games.__main__ import build_app, parse_args
from met_games.games.math.adaptive import stored_levels
from met_games.games.math.history import load_bests, load_history, load_runs
from met_games.games.math.prob import fmt
from met_games.games.math.screens.flow import FlowScreen
from met_games.games.math.screens.lobby import MathLobby
from met_games.games.math.screens.prob import ProbReportScreen, ProbScreen
from met_games.games.math.screens.report import ReportScreen
from met_games.games.math.screens.stats import StatsScreen
from met_games.games.math.ui import MENU
from met_games.pause import PauseMenu

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


def text_of(screen, selector):
    return str(screen.query_one(selector, Static).render())


async def wait(pilot, clock, seconds):
    clock.t += seconds
    pilot.app.screen.sync()
    await pilot.pause()


async def submit(pilot, clock, text, seconds=2.0):
    clock.t += seconds
    if text:
        await pilot.press(*text)
    await pilot.press("enter")
    await pilot.pause()


def test_cli_modes():
    assert parse_args(["math", "--mode", "flow"]).mode == "flow"
    assert parse_args(["math", "--mode", "prob", "--difficulty", "adaptive"]).difficulty == "adaptive"
    with pytest.raises(SystemExit):
        parse_args(["math", "--mode", "flow", "--difficulty", "adaptive"])


async def test_every_lobby_entry_is_live():
    app, clock = make_app("math")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        assert all(kind != "soon" for kind, _, _ in MENU)
        await pilot.press(*["down"] * 6)  # SURVIVAL, CHAIN, ESTIMATE, ZETAMAC, OPTIVER-STYLE, FLOW-STYLE
        assert lobby.mode == "flow" and "60 questions in 6:00" in text_of(lobby, "#rules")
        assert "unofficial practice format" in text_of(lobby, "#rules").lower()
        assert "fixed format" in text_of(lobby, "#difficulty")
        await pilot.press("down")
        assert lobby.mode == "prob" and "20 probability questions" in text_of(lobby, "#rules")
        pills = text_of(lobby, "#difficulty").split("\n")[0]
        assert "ADAPTIVE" in pills and "CUSTOM" not in pills
        await pilot.press("right", "right")  # MEDIUM → HARD → ADAPTIVE
        assert lobby.config("prob").difficulty == "adaptive"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ProbScreen) and app.screen.run.board == "adaptive"


async def test_a_full_flow_style_run_to_the_report():
    app, clock = make_app("math", "--mode", "flow", "--seed", "3")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FlowScreen)
        assert "unofficial practice format" in text_of(screen, "#strip")
        run = screen.run
        await submit(pilot, clock, run.problem.answer_text)
        await submit(pilot, clock, run.problem.answer_text + "9")  # wrong: still moves on
        await submit(pilot, clock, "")  # empty Enter: a skip
        assert run.answered == 3 and (run.correct, run.wrong, run.skipped) == (1, 1, 1)
        strip = text_of(screen, "#strip")
        assert "ANSWERED 3/60" in strip and "✓ ?" in strip and "✗ ?" in strip and "SCORE ?" in strip
        assert "✓ 1" not in strip and "wrong" not in text_of(screen, "#question")  # no feedback mid-run
        await pilot.press("escape")  # the board hides; the clock keeps running
        await pilot.pause()
        menu = app.screen
        assert isinstance(menu, PauseMenu) and "keeps running" in text_of(menu, "#pause-text")
        left = run.time_left_ms
        clock.t += 20
        screen.sync()
        assert run.time_left_ms == left - 20_000
        await pilot.press("r")
        await pilot.pause()
        assert "your pace" in text_of(screen, "#pace")
        for i in range(57):
            await submit(pilot, clock, run.problem.answer_text if i % 4 else "", 1.0)
        report = app.screen
        assert isinstance(report, ReportScreen) and run.over and run.answered == 60
        assert report.score_title() == "SCORE" and run.correct == 1 + 42
        assert report.query("#flow-rows") and len(report.flow_table().rows) == 60
        assert load_bests()["flow/standard"]["correct"] == 43 and len(load_history()) == 60
        assert load_runs()[-1]["mode"] == "flow"
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)


async def test_flow_times_out_at_six_minutes_even_paused():
    app, clock = make_app("math", "--mode", "flow", "--seed", "4")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        await submit(pilot, clock, screen.run.problem.answer_text)
        await pilot.press("escape")
        await pilot.pause()
        clock.t += 400
        screen.sync()
        await pilot.pause()
        report = app.screen
        assert isinstance(report, ReportScreen) and screen.run.over and screen.run.answered == 1
        assert len(report.flow_table().rows) == 60  # the questions you didn't reach are listed too


async def test_a_probability_drill_with_a_known_mistake():
    app, clock = make_app("math", "--mode", "prob", "--difficulty", "medium", "--seed", "2")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ProbScreen)
        assert "dice · cards · coins · expected value" in text_of(screen, "#strip")
        run = screen.run
        while not run.problem.mistakes:
            await pilot.press("s")
            await pilot.pause()
        p = run.problem
        wrong, why = p.mistakes[0]
        await submit(pilot, clock, fmt(wrong))
        panel = text_of(screen, "#why")
        assert f"✗ {fmt(wrong)}" in panel and f"it was {p.answer_text}" in panel
        assert p.explanation[0] in panel and why in panel
        so_far = screen.so_far_text()
        assert so_far.columns[1]._cells[0].plain == f"✗ {fmt(wrong)}" and so_far.columns[0]._cells[0].plain == \
            p.answer_text
        await submit(pilot, clock, run.problem.answer_text)
        assert "✓ right" in text_of(screen, "#why") and why not in text_of(screen, "#why")
        assert "✓ 1" in text_of(screen, "#strip") and "✗ 1" in text_of(screen, "#strip")
        while not run.over:
            await submit(pilot, clock, run.problem.answer_text, 1.0)
        report = app.screen
        assert isinstance(report, ProbReportScreen)
        misses = text_of(report, "#misses")
        assert p.explanation[0] in misses and why in misses
        assert run.correct == 20 - run.skipped - 1 and load_bests()["prob/medium"]["correct"] == run.correct
        assert all(r["family"] == "prob" for r in load_history())
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)


async def test_the_adaptive_prob_level_moves_and_shows_in_stats():
    app, clock = make_app("math", "--mode", "prob", "--difficulty", "adaptive", "--seed", "5")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        run = screen.run
        assert "prob L3" in text_of(screen, "#question")
        for _ in range(3):
            await submit(pilot, clock, run.problem.answer_text, 3.0)
        assert run.ladder.level("prob") == 4 and "prob L4" in text_of(screen, "#question")
        assert "▲ from L3" in text_of(screen, "#question")
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert isinstance(app.screen, ProbReportScreen) and "L3 → L4" in text_of(app.screen, "#prob-score")
        assert stored_levels()["prob"] == 4
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        stats = app.screen
        prob_line = next(line for line in text_of(stats, "#levels").splitlines() if line.startswith("prob"))
        assert isinstance(stats, StatsScreen) and "L4" in prob_line
        await pilot.press("left", "left")  # wraps: OPTIVER-STYLE, PROBABILITY DRILL
        assert stats.mode == "prob"
        await pilot.press("down", "down")  # MEDIUM → HARD → ADAPTIVE
        assert stats.difficulty == "adaptive" and "correct: 3" in text_of(stats, "#spark")


async def test_a_counting_question_answered_in_order_shows_why():
    app, clock = make_app("math", "--mode", "prob", "--difficulty", "medium", "--seed", "7")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        run = screen.run
        assert "dice · cards · coins · expected value · counting" in text_of(screen, "#strip")
        while run.problem.form != "count" or "order doesn't matter" not in run.problem.text:
            assert "a/b or 3-dp decimal" in text_of(screen, "#question")
            await pilot.press("s")
            await pilot.pause()
        p = run.problem
        assert "whole number" in text_of(screen, "#question")
        wrong, why = next((v, w) for v, w in p.mistakes if "ordered draws" in w)
        await submit(pilot, clock, f"{wrong.numerator:,}")  # with commas, the way it's printed
        panel = text_of(screen, "#why")
        assert f"it was {p.answer_text}" in panel and p.answer_text == f"{p.answer.numerator:,}"
        assert why in panel and p.explanation[-1] in panel
        assert run.last.mistake == why and run.last.outcome == "wrong"
