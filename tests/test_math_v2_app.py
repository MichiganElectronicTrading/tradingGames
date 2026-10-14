"""Mental Math v2 Pilot tests on a fake clock: the lobby, Chain to a break, a full Estimate run, an Adaptive Sprint
whose level moves mid-run, and MY STATS with its focus drill."""

from datetime import date, timedelta

import pytest
from textual.widgets import Static

from met_games import storage
from met_games.__main__ import build_app, parse_args
from met_games.games.math.adaptive import LEVELS_FILE, save_levels, stored_levels
from met_games.games.math.estimate import two_dp
from met_games.games.math.history import load_bests, load_history, load_runs
from met_games.games.math.ladder import TRACKS
from met_games.games.math.screens.chain import ChainReportScreen, ChainScreen
from met_games.games.math.screens.custom import MathCustomScreen
from met_games.games.math.screens.estimate import EstimateReportScreen, EstimateScreen
from met_games.games.math.screens.lobby import MathLobby
from met_games.games.math.screens.play import RunScreen
from met_games.games.math.screens.report import ReportScreen
from met_games.games.math.screens.stats import StatsScreen
from met_games.pause import PauseMenu
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


def text_of(screen, selector):
    return str(screen.query_one(selector, Static).render())


async def wait(pilot, clock, seconds):
    clock.t += seconds
    pilot.app.screen.sync()
    await pilot.pause()


async def submit(pilot, clock, text, seconds=1.0):
    clock.t += seconds
    await pilot.press(*text, "enter")
    await pilot.pause()


# ── the lobby ───────────────────────────────────────────────────────────────


async def test_lobby_lists_the_v2_modes_and_pills_follow_the_mode():
    app, clock = make_app("math")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        lobby = app.screen
        rows = [str(r) for r in lobby.query_one("#menu").rows]
        assert any("CHAIN" in r for r in rows) and any("ESTIMATE" in r for r in rows)
        assert any("PROBABILITY DRILL" in r for r in rows) and not any("IMC" in r for r in rows)
        assert any("FLOW-STYLE 60/6" in r for r in rows) and not any("soon" in r for r in rows)
        assert not any("NEW" in r for r in rows)
        await pilot.press("right", "right", "right")  # MEDIUM → HARD → CUSTOM → ADAPTIVE
        assert lobby.difficulty == "adaptive" and "ADAPTIVE" in text_of(lobby, "#difficulty")
        assert "3 fast right answers" in text_of(lobby, "#rules")
        await pilot.press("down", "down")  # CHAIN: no ADAPTIVE pill — it plays MEDIUM, your pick is kept
        assert lobby.mode == "chain" and "ADAPTIVE" not in text_of(lobby, "#difficulty")
        assert lobby.config("chain").difficulty == "medium" and "running number" in text_of(lobby, "#rules")
        await pilot.press("down")  # ESTIMATE: EASY MEDIUM HARD only
        pills = text_of(lobby, "#difficulty").split("\n")[0]
        assert "CUSTOM" not in pills and "ADAPTIVE" not in pills and "15 questions" in text_of(lobby, "#rules")
        await pilot.press("up", "up")
        assert lobby.config("sprint").difficulty == "adaptive"
        assert "first one seeds" in text_of(lobby, "#levels")
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is lobby


async def test_chain_custom_from_the_lobby():
    app, clock = make_app("math", "--seed", "6")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("right", "right", "down", "down", "enter")  # CUSTOM · CHAIN
        await pilot.pause()
        custom = app.screen
        assert isinstance(custom, MathCustomScreen) and custom.rows[0] == "step" and custom.step_s == 12
        await pilot.press(*["left"] * 6)  # 12s → 6s
        await pilot.press("down", "right")  # ± stays on
        await pilot.press("down", "right")  # × off
        await pilot.press("down", "right")  # ÷ off
        assert custom.config().ops == ("pm", "pct") and custom.config().step_s == 6
        await pilot.press("enter")
        await pilot.pause()
        run = app.screen.run
        assert isinstance(app.screen, ChainScreen) and run.rules.step_ms == 6_000 and run.board == "custom"
        assert run.link.kind in ("pm", "pct")


# ── Chain ───────────────────────────────────────────────────────────────────


async def test_chain_to_a_break_then_report_then_lobby():
    app, clock = make_app("math", "--mode", "chain", "--seed", "4")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChainScreen)
        run = screen.run
        assert str(run.carry) in text_of(screen, "#carry") and run.link.op_text in text_of(screen, "#link")
        for _ in range(3):
            await submit(pilot, clock, str(run.link.answer), 2.0)
        assert run.length == 3 and "LENGTH 3" in text_of(screen, "#strip")
        assert "no links yet" not in text_of(screen, "#log")
        await pilot.press("enter")  # nothing typed: nothing happens
        assert not run.over
        await pilot.press("escape")  # paused: the step clock freezes
        await pilot.pause()
        assert isinstance(app.screen, PauseMenu)
        clock.t += 60
        await pilot.press("r")
        await pilot.pause()
        screen.sync()
        assert not run.over and run.time_left_ms == 12_000
        right = run.link.answer
        await submit(pilot, clock, str(right + 1))
        report = app.screen
        assert isinstance(report, ChainReportScreen) and run.over and run.broke.outcome == "wrong"
        broke = text_of(report, "#broke-at")
        assert f"link 4: {run.broke.link.text}" in broke and str(right + 1) in broke and str(right) in broke
        assert report.query("#new-best")
        assert load_bests()["chain/medium"]["length"] == 3 and load_runs()[-1]["length"] == 3
        assert [r["outcome"] for r in load_history()] == ["correct"] * 3 + ["wrong"]
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)


async def test_chain_times_out_and_hard_hides_the_carry():
    app, clock = make_app("math", "--mode", "chain", "--difficulty", "hard", "--seed", "9")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        run = screen.run
        assert "?" not in text_of(screen, "#link").split("=")[0]
        await submit(pilot, clock, str(run.link.answer))
        assert run.hidden and "hidden" in text_of(screen, "#carry") and "hidden on HARD" in text_of(screen, "#log")
        assert "?" in text_of(screen, "#link") and str(run.carry) not in text_of(screen, "#link").split("=")[0]
        await wait(pilot, clock, 9.9)
        assert isinstance(app.screen, ChainScreen)
        await wait(pilot, clock, 0.2)
        report = app.screen
        assert isinstance(report, ChainReportScreen) and run.broke.outcome == "timeout"
        assert "time ran out" in text_of(report, "#broke-at")
        await pilot.press("r")  # again: a fresh chain on the same board
        await pilot.pause()
        assert isinstance(app.screen, ChainScreen) and app.screen.run.board == "hard" and app.screen.run.length == 0


# ── Estimate ────────────────────────────────────────────────────────────────


async def test_a_full_estimate_run():
    app, clock = make_app("math", "--mode", "estimate", "--difficulty", "easy", "--seed", "2")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EstimateScreen)
        run = screen.run
        assert run.question.text in text_of(screen, "#question")
        await wait(pilot, clock, 15)  # the first one times out
        assert len(run.rows) == 1 and run.rows[0].points == 0
        for i in range(14):
            await submit(pilot, clock, two_dp(run.question.exact), 3.0 if i % 2 else 6.0)
        report = app.screen
        assert isinstance(report, EstimateReportScreen) and run.over and len(run.rows) == 15
        assert run.count("full") == 14 and run.points == 7 * 200 + 7 * 150
        assert "FULL ≤1%" in text_of(report, "#bands") and "timeouts" in text_of(report, "#bands")
        assert load_bests()["estimate/easy"]["points"] == 2450 and load_runs()[-1]["full"] == 14
        assert len(load_history()) == 15
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)


# ── Adaptive ────────────────────────────────────────────────────────────────


async def test_an_adaptive_sprint_moves_a_level_mid_run():
    app, clock = make_app("math", "--mode", "sprint", "--difficulty", "adaptive", "--seed", "3")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RunScreen)
        run = screen.run
        assert run.board == "adaptive" and run.ladder is not None and run.problem.level == "L3"
        assert screen.query_one("#by-type").parent.border_title == "LEVELS"
        assert "L3" in text_of(screen, "#problem")
        while not run.ladder.changes:
            clock.t += 1.0  # every answer within its track's target
            await pilot.press(*run.problem.answer_text)
            await pilot.pause()
        track, old, new = run.ladder.changes[0]
        assert (old, new) == (3, 4)
        assert "▲ from L3" in text_of(screen, "#by-type") and "L3 → L4" in text_of(screen, "#by-type")
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert isinstance(app.screen, ReportScreen)
        assert stored_levels()[track] == 4 and load_runs()[-1]["difficulty"] == "adaptive"
        assert "sprint/adaptive" in load_bests()


# ── MY STATS ────────────────────────────────────────────────────────────────


async def test_stats_navigation_and_the_focus_drill():
    today = date.today()
    save_levels({t: 5 for t in TRACKS}, today - timedelta(days=8))
    save_levels({**{t: 5 for t in TRACKS}, "pct": 3}, today)
    storage.append_jsonl("math_runs.jsonl", {"date": "2026-01-02", "mode": "chain", "difficulty": "hard",
                                             "length": 7, "points": 900})
    storage.append_jsonl("math_runs.jsonl", {"date": "2026-01-03", "mode": "chain", "difficulty": "hard",
                                             "length": 11, "points": 1500})
    app, clock = make_app("math", "--seed", "12")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        stats = app.screen
        assert isinstance(stats, StatsScreen)
        assert stats.query_one("#stats-top", TopBar).round_text.startswith("2 runs · since 2026-01-02")
        assert stats.mode == "sprint" and stats.difficulty == "medium" and "no SPRINT runs" in text_of(stats, "#spark")
        await pilot.press("right", "right")  # CHAIN
        await pilot.press("down")  # HARD
        assert (stats.mode, stats.difficulty) == ("chain", "hard")
        spark = text_of(stats, "#spark")
        assert "▁▁██" in spark and "chain length: 7 → 9 → 11" in spark
        await pilot.press("left", "left", "left")  # wraps to OPTIVER-STYLE
        assert stats.mode == "optiver" and stats.difficulty == "standard"
        levels = text_of(stats, "#levels")
        assert "L3  ▼" in levels and "L5  ·" in levels
        assert "%" in text_of(stats, "#focus") and "down 2 levels in 7 days" in text_of(stats, "#focus")
        assert "— until 20 runs" in str(stats.medians_table().caption)
        await pilot.press("f")
        await pilot.pause()
        drill = app.screen
        assert isinstance(drill, RunScreen) and drill.run.focus == "pct" and drill.run.mode == "drill"
        assert drill.run.problem.level == "L3" and drill.run.problem.family == "pct"
        clock.t += 1
        await pilot.press(*drill.run.problem.answer_text)
        await pilot.pause()
        await wait(pilot, clock, 120)
        assert isinstance(app.screen, ReportScreen) and not app.screen.query("#new-best")
        assert load_bests() == {} and load_runs()[-1]["focus"] == "pct"
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, MathLobby)
        assert storage.read_json(LEVELS_FILE, {})["levels"]["pct"] >= 3
