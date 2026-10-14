"""Mental Math display size: at NORMAL every run screen draws exactly what it drew before the setting existed; at
LARGE / HUGE problems and answers draw big (word problems stay NORMAL), fall back a size at a time when they don't
fit (each Optiver-style choice on its own), and input still works on the raw typed string."""

import json
from pathlib import Path

import pytest
from normal_screens import capture
from textual.widgets import Static

from met_games import settings
from met_games.__main__ import build_app, parse_args
from met_games.bigtext import HUGE, LARGE, NORMAL, ROWS, fit, render, width
from met_games.games.math.screens.display import ANSWER_SIZE, PROBLEM_SIZE, answer_rows, choice_text, problem_rows
from met_games.games.math.screens.play import OptiverScreen, RunScreen
from met_games.settings_screen import SettingsScreen

REFERENCE = Path(__file__).parent / "snapshots" / "math_normal_screens.json"
SIZE = (150, 50)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def text_of(screen, selector):
    return str(screen.query_one(selector, Static).render())


# ── NORMAL changes nothing ──────────────────────────────────────────────────


async def test_all_normal_draws_every_run_screen_exactly_as_before():
    """The reference was recorded from the screens before display size existed (tests/normal_screens.py)."""
    assert settings.get("math", PROBLEM_SIZE, NORMAL) == NORMAL
    assert await capture() == json.loads(REFERENCE.read_text())


async def test_explicit_normal_is_the_same_as_no_settings_file():
    settings.set("math", PROBLEM_SIZE, NORMAL)
    settings.set("math", ANSWER_SIZE, NORMAL)
    assert await capture() == json.loads(REFERENCE.read_text())


# ── fallback ────────────────────────────────────────────────────────────────


def test_a_long_hard_problem_drops_huge_to_large_to_normal_in_a_narrow_panel():
    text = "8457 + 3916 ="
    assert len(problem_rows(text, HUGE, 200)) == ROWS[HUGE]
    assert len(problem_rows(text, HUGE, width(text, HUGE) - 1)) == ROWS[LARGE]
    assert problem_rows(text, HUGE, width(text, LARGE) - 1) is None  # NORMAL: drawn exactly as ever


def test_a_desk_problem_stays_normal_at_huge():
    assert problem_rows("bid 91.18 / ask 91.68 · buy 400 at the ask, sell at the bid · P&L = ? =", HUGE, 500) is None
    assert problem_rows("60% of 814 =", HUGE, 500) is None and problem_rows("√581", HUGE, 500) is None


def test_the_answer_line_shrinks_as_you_type_instead_of_clipping():
    room = 30
    sizes = []
    for n in range(1, 12):
        rows = answer_rows("8" * n, HUGE, room)
        sizes.append(NORMAL if rows is None else {3: LARGE, 5: HUGE}[len(rows)])
        if rows:
            assert len(rows[0]) <= room and rows[0].endswith("▌")
    assert sizes[0] == HUGE and LARGE in sizes and sizes[-1] == NORMAL
    assert sizes == sorted(sizes, key=[NORMAL, LARGE, HUGE].index, reverse=True)  # only ever shrinks


def test_optiver_choices_fall_back_one_box_at_a_time():
    from rich.text import Text

    badge = Text(" 1 ")
    room = 5 + width("0.375", HUGE)  # badge + gap, then exactly a HUGE 0.375
    short, rows = choice_text(badge, "0.375", HUGE, room)
    assert rows == ROWS[HUGE]
    longer = choice_text(badge, "0.3755", HUGE, room)
    assert longer is not None and longer[1] == ROWS[LARGE]  # this box alone drops to LARGE
    assert choice_text(badge, "0.37555555555", HUGE, room) is None  # and this one to NORMAL


# ── Pilot ───────────────────────────────────────────────────────────────────


async def test_set_sizes_in_settings_then_sprint_and_optiver_draw_big():
    app = build_app(parse_args(["math", "--seed", "5"]))
    clock = FakeClock()
    app.math_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("comma")
        await pilot.pause()
        s = app.screen
        assert isinstance(s, SettingsScreen)
        await pilot.press("right", "right")  # PROBLEM SIZE → HUGE
        await pilot.press("down", "right")  # ANSWER SIZE → LARGE
        await pilot.pause()
        assert settings.get("math", PROBLEM_SIZE, NORMAL) == HUGE and settings.get("math", ANSWER_SIZE, NORMAL) == LARGE
        assert "◂   HUGE   ▸" in text_of(s, "#settings-list") and "◂  LARGE   ▸" in text_of(s, "#settings-list")
        await pilot.press("escape", "enter")  # back, then SPRINT
        await pilot.pause()
        run_screen = app.screen
        assert isinstance(run_screen, RunScreen) and run_screen.problem_size == HUGE
        run = run_screen.run
        while "%" in run.problem.text or run.problem.family == "desk" or not render(run.problem.text, HUGE):
            await pilot.press("tab")
            await pilot.pause()
        problem = text_of(run_screen, "#problem")
        big = render(f"{run.problem.text} =", HUGE)
        fits = len(big[0]) <= run_screen.query_one("#problem", Static).content_size.width
        expect = big if fits else render(f"{run.problem.text} =", LARGE)
        assert all(row in problem for row in expect) and f"{run.problem.text}  =" not in problem
        await pilot.press(*run.problem.answer_text[:1])
        await pilot.pause()
        assert all(row in text_of(run_screen, "#problem") for row in
                   [r + " ▌" for r in render(run.problem.answer_text[:1], LARGE)])  # the typed line, LARGE
        await pilot.press("ctrl+e")
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down", "down", "down", "down", "enter")  # OPTIVER-STYLE
        await pilot.pause()
        opt = app.screen
        assert isinstance(opt, OptiverScreen) and opt.answer_size == LARGE
        boxes = [opt.query_one(f"#option-{i}", Static) for i in range(4)]
        for i, box in enumerate(boxes):
            value = opt.run.question.options[i]
            content = str(box.render())
            if render(value, LARGE):
                assert all(row in content for row in render(value, LARGE)) and box.outer_size.height == 3 + 2
            assert content.startswith(f" {i + 1} ")  # the badge stays normal size


async def test_typing_still_locks_on_an_exact_match_at_huge():
    settings.set("math", PROBLEM_SIZE, HUGE)
    settings.set("math", ANSWER_SIZE, HUGE)
    app = build_app(parse_args(["math", "--mode", "zetamac", "--seed", "4"]))
    clock = FakeClock()
    app.math_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        screen = app.screen
        run = screen.run
        for _ in range(5):
            answer = run.problem.answer_text
            assert render(f"{run.problem.text} =", HUGE)[0] in text_of(screen, "#problem")
            clock.t += 1
            await pilot.press(*answer)
            await pilot.pause()
            assert run.attempts[-1].given == answer and run.attempts[-1].outcome == "correct"
        assert run.correct == 5 and run.typed == ""


async def test_r_resets_the_section_to_normal():
    settings.set("math", PROBLEM_SIZE, HUGE)
    settings.set("math", ANSWER_SIZE, LARGE)
    app = build_app(parse_args(["math"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("comma")
        await pilot.pause()
        assert "HUGE" in text_of(app.screen, "#settings-list")
        await pilot.press("r")
        await pilot.pause()
        assert settings.get("math", PROBLEM_SIZE, None) == NORMAL and settings.get("math", ANSWER_SIZE, None) == NORMAL
        assert "HUGE" not in text_of(app.screen, "#settings-list")


async def test_sizes_persist_across_launches():
    app = build_app(parse_args(["math"]))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.press("comma", "right")
        await pilot.pause()
    again = build_app(parse_args(["math", "--mode", "sprint"]))
    async with again.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert again.screen.problem_size == LARGE


def test_fit_is_only_drawing():
    assert fit("1/2", HUGE, 0) == (NORMAL, ["1/2"])
