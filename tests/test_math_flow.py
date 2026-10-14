"""Flow-style 60 in 6: 60 questions, wrong answers move on, an empty Enter skips, nothing shown until the end, the
pace math, and the 6:00 clock."""

from fractions import Fraction as F

import pytest

from met_games.games.math.config import FLOW, MathConfig
from met_games.games.math.flow import FLOW_MS, QUESTIONS, FlowRun, flow_problems
from met_games.games.math.history import file_run, load_bests
from met_games.games.math.problems import CORE, DECFRAC, HARD, MEDIUM, accepts


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def flow(seed=3):
    return FlowRun(MathConfig(mode=FLOW), seed)


def enter(run, text, after_ms=1000):
    run.advance_to(run.now + after_ms)
    for ch in text:
        run.type(ch)
    return run.submit()


def test_sixty_core_and_decfrac_questions_at_medium_to_hard():
    qs = flow_problems(7)
    assert len(qs) == QUESTIONS == 60 and qs == flow_problems(7) and qs != flow_problems(8)
    assert {p.family for p in qs} == {CORE, DECFRAC} and sum(p.family == CORE for p in qs) == 30
    assert {p.level for p in qs} == {MEDIUM, HARD}
    assert FLOW_MS == 360_000 and flow().board == "standard"


def test_wrong_answers_advance_and_empty_enter_skips():
    run = flow()
    first = run.problem
    a = enter(run, first.answer_text + "1")  # wrong
    assert a.outcome == "wrong" and run.problem is run.questions[1] and run.typed == ""
    b = enter(run, "")  # nothing typed: a skip
    assert b.outcome == "skipped" and run.answered == 2
    c = enter(run, run.problem.answer_text)
    assert c.outcome == "correct" and accepts(c.problem, c.given)
    assert (run.correct, run.wrong, run.skipped) == (1, 1, 1)
    assert [x.problem for x in run.attempts] == run.questions[:3]  # in order, no going back


def test_typing_never_locks_an_answer():
    run = flow()
    for ch in run.problem.answer_text:
        run.type(ch)
    assert run.answered == 0 and run.typed == run.questions[0].answer_text


def test_sixty_answers_end_the_run():
    run = flow(5)
    for i in range(60):
        enter(run, run.problem.answer_text if i % 3 else "", 500)
    assert run.over and run.answered == 60 and run.correct == 40 and run.skipped == 20
    assert run.submit() is None


def test_pace_math():
    run = flow()
    assert run.pace() == (None, F(360, 60)) and run.on_pace()
    for _ in range(10):
        enter(run, "", 5_000)  # 50s for 10: 5s each; needed (360 − 50) / 50 = 6.2s
    assert run.pace() == (F(5), F(310, 50)) and run.on_pace()
    run.advance_to(run.now + 30_000)  # 80s for 10 → 8s each; needed 280 / 50 = 5.6s
    assert run.pace() == (F(8), F(280, 50)) and not run.on_pace()
    run2 = flow()
    enter(run2, "", 6_000)  # exactly the needed 6s: at pace counts as on pace
    assert run2.pace() == (F(6), F(6)) and run2.on_pace()


def test_times_out_at_six_minutes():
    run = flow()
    enter(run, run.problem.answer_text)
    run.advance_to(FLOW_MS - 1)
    assert not run.over and run.time_left_ms == 1
    run.advance_to(FLOW_MS)
    assert run.over and run.answered == 1


def test_bests_are_the_correct_count():
    run = flow()
    for _ in range(3):
        enter(run, run.problem.answer_text)
    run.end()
    _, beaten = file_run(run)
    assert beaten == ["correct"] and load_bests()["flow/standard"]["correct"] == 3
    assert {a.problem.level for a in run.attempts} <= {MEDIUM, HARD}
