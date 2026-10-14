"""The Probability drill: 20 questions in 10:00, feedback after each answer (with the known-mistake message), skips,
the tolerance in play, the adaptive prob level, and what gets logged."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from met_games import storage
from met_games.games.math.adaptive import LEVELS_FILE, load_levels, save_levels
from met_games.games.math.config import ADAPTIVE, PROB_DRILL, MathConfig
from met_games.games.math.history import file_arcade, load_bests, load_history, load_runs
from met_games.games.math.ladder import PROB_TRACK, TRACKS
from met_games.games.math.prob import fmt
from met_games.games.math.probdrill import PROB_MS, QUESTIONS, ProbRun
from met_games.games.math.problems import EASY, HARD, MEDIUM


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def drill(difficulty=MEDIUM, seed=4, **kw):
    return ProbRun(MathConfig(mode=PROB_DRILL, difficulty=difficulty), seed, **kw)


def enter(run, text, after_ms=2000):
    run.advance_to(run.now + after_ms)
    for ch in text:
        run.type(ch)
    return run.submit()


def test_twenty_questions_then_it_ends():
    run = drill(HARD)
    assert QUESTIONS == 20 and PROB_MS == 600_000
    for _ in range(20):
        assert enter(run, run.problem.answer_text).outcome == "correct"
    assert run.over and run.correct == 20 and run.problem is None and run.submit() is None


def test_ten_minutes_end_it():
    run = drill()
    run.advance_to(PROB_MS - 1)
    assert not run.over
    run.advance_to(PROB_MS)
    assert run.over and run.answered == 0


def test_feedback_after_each_answer_with_the_mistake_message():
    run = drill(MEDIUM, 2)
    while not run.problem.mistakes:
        run.skip()
    p = run.problem
    wrong, why = p.mistakes[0]
    a = enter(run, fmt(wrong))
    assert a.outcome == "wrong" and a.mistake == why and run.last is a and a.problem is p
    assert run.problem is not p  # it moved on; the feedback is about the last answer
    b = enter(run, run.problem.answer_text)
    assert b.correct and b.mistake is None
    c = enter(run, "999")
    assert c.outcome == "wrong" and c.mistake is None  # wrong, but no known mistake


def test_decimals_in_tolerance_count():
    run = drill(HARD, 1)
    for _ in range(10):
        if run.problem.form == "count":  # counting questions take whole numbers only (see test_math_prob)
            run.skip()
            continue
        a = run.problem.answer
        three = (Decimal(a.numerator) / Decimal(a.denominator)).quantize(Decimal("0.001"))  # rounded: ≤ 0.0005 off
        assert enter(run, str(three)).correct


def test_skip_and_junk():
    run = drill()
    for ch in "1/":
        run.type(ch)
    assert run.submit() is None and run.answered == 0  # not a number yet
    s = run.skip()
    assert s.outcome == "skipped" and s.given == "" and run.skipped == 1 and run.typed == ""


def test_the_adaptive_prob_level_moves_and_is_saved_on_its_own():
    save_levels({t: 5 for t in TRACKS}, date.today() - timedelta(days=1))
    run = drill(ADAPTIVE, 6)
    assert run.board == ADAPTIVE and run.problem.level == "L3" and run.ladder.levels == {PROB_TRACK: 3}
    for _ in range(3):
        enter(run, run.problem.answer_text, 5_000)  # within the 15s target
    assert run.ladder.level(PROB_TRACK) == 4 and run.problem.level == "L4"
    enter(run, "999")
    assert run.ladder.level(PROB_TRACK) == 3
    for _ in range(6):
        enter(run, run.problem.answer_text, 1_000)
    run.end()
    beaten, _ = file_arcade(run)
    saved = storage.read_json(LEVELS_FILE, {})["levels"]
    assert saved[PROB_TRACK] == 5 and all(saved[t] == 5 for t in TRACKS)  # the sprint tracks kept theirs
    assert load_levels(tracks=(PROB_TRACK,)) == {PROB_TRACK: 5} and load_levels() == {t: 5 for t in TRACKS}
    assert beaten == ["correct"] and load_bests()["prob/adaptive"]["correct"] == 9


def test_logged_lines_carry_the_prob_track_and_bests_per_difficulty():
    run = drill(HARD, 3)
    enter(run, run.problem.answer_text)
    run.skip()
    enter(run, "999")
    run.end()
    file_arcade(run)
    rows = load_history()
    assert [r["outcome"] for r in rows] == ["correct", "skipped", "wrong"]
    assert all(r["family"] == "prob" and r["track"] == "prob" and r["level"] == HARD for r in rows)
    assert load_runs()[-1]["correct"] == 1 and load_bests()["prob/hard"]["correct"] == 1
    assert [s for s, _, _ in run.by_subtype()] and len(run.misses) == 2


def test_history_seeds_the_prob_level():
    for _ in range(3):
        run = drill(HARD, 8)
        for _ in range(10):
            enter(run, run.problem.answer_text)
        run.end()
        file_arcade(run)
    assert load_levels(tracks=(PROB_TRACK,)) == {PROB_TRACK: 9}
