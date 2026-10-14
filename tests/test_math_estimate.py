"""Estimate: exact answers, bands at exactly 1/5/10% and just over, the speed multiplier at 4.0s and 8.0s, timeouts,
comma parsing, never a round answer, and a run's points and log."""

from decimal import Decimal as D
from fractions import Fraction as F
from math import isqrt

import pytest

from met_games.games.math.config import ESTIMATE, MathConfig
from met_games.games.math.estimate import (
    DIV,
    FULL,
    HALF,
    KINDS,
    MISS,
    MUL,
    PCT_OF,
    QUARTER,
    QUESTION_MS,
    SMALL,
    SQRT,
    EstimateRun,
    Question,
    band,
    is_round,
    make_questions,
    off_by,
    parse_guess,
    percent_text,
    points_text,
    score,
    speed,
    two_dp,
)
from met_games.games.math.history import file_arcade, load_bests, load_history, load_runs
from met_games.games.math.problems import EASY, HARD, MEDIUM


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def q(exact="1000"):
    return Question(MUL, "?", D(exact), D(0), D(0))


@pytest.mark.parametrize("level", [EASY, MEDIUM, HARD])
def test_exact_answers_are_exact_to_decimal_precision_and_never_round(level):
    for seed in range(60):
        qs = make_questions(seed, level)
        assert len(qs) == 15 and sorted(x.kind for x in qs) == sorted(k for k in KINDS for _ in range(3))
        for x in qs:
            a, b = F(x.a), F(x.b)
            e = F(x.exact)
            if x.kind in (MUL, SMALL):
                assert e == a * b
            elif x.kind == PCT_OF:
                assert e == a * b / 100
            elif x.kind == DIV:
                assert abs(e - a / b) <= F(1, 2 * 10**8) and x.exact.as_tuple().exponent == -8
            else:  # √ to 8 dp: the true root is within half a unit of the 8th place
                half = F(1, 2 * 10**8)
                assert (e - half) ** 2 <= a <= (e + half) ** 2 and x.exact.as_tuple().exponent == -8
                assert isqrt(int(x.a)) ** 2 != int(x.a)  # never a perfect square
            assert not is_round(x.exact) and x.exact >= 1


def test_operand_shapes_by_difficulty():
    for x in make_questions(1, EASY) + make_questions(2, EASY):
        if x.kind == MUL:
            assert 100 <= x.a <= 999 and 10 <= x.b <= 99 and x.a == int(x.a) and x.b == int(x.b)
        if x.kind == SMALL:
            assert 1000 <= x.a <= 9999 and D("0.01") <= x.b < D("0.1") and x.b.as_tuple().exponent == -4
    for x in make_questions(3, MEDIUM):
        if x.kind in (MUL, DIV, PCT_OF):
            assert x.a.as_tuple().exponent == -1 and len(x.a.as_tuple().digits) == 4
        if x.kind == SQRT:
            assert 1000 <= x.a <= 9999
    for x in make_questions(4, HARD):
        if x.kind in (MUL, DIV, PCT_OF):
            assert -x.a.as_tuple().exponent in (2, 3) and len(x.a.as_tuple().digits) in (4, 5)
        if x.kind == SQRT:
            assert 10000 <= x.a <= 99999


def test_round_means_under_three_significant_digits():
    assert is_round(D("4500")) and is_round(D("0.25")) and is_round(D("30"))
    assert not is_round(D("4560")) and not is_round(D("24.10394159")) and not is_round(D("528.93"))


def test_bands_are_inclusive_at_1_5_and_10_percent():
    exact = D("1000")
    assert band(off_by(F(1010), exact)) == (FULL, 100) and band(off_by(F(990), exact)) == (FULL, 100)
    assert band(off_by(F("1010.001"), exact)) == (HALF, 50)
    assert band(off_by(F(1050), exact)) == (HALF, 50) and band(off_by(F(950), exact)) == (HALF, 50)
    assert band(off_by(F("1050.001"), exact)) == (QUARTER, 25)
    assert band(off_by(F(1100), exact)) == (QUARTER, 25) and band(off_by(F(900), exact)) == (QUARTER, 25)
    assert band(off_by(F("1100.001"), exact)) == (MISS, 0) and band(off_by(F("899.999"), exact)) == (MISS, 0)


def test_speed_multiplier_at_4_and_8_seconds():
    assert [speed(ms) for ms in (0, 4_000, 4_001, 8_000, 8_001, 15_000)] == [2, 2, F(3, 2), F(3, 2), 1, 1]
    assert score(q(), "1000", 4_000).points == 200 and score(q(), "1000", 4_001).points == 150
    assert score(q(), "1100", 8_000).points == F(75, 2) and score(q(), "1100", 8_001).points == 25
    assert points_text(F(75, 2)) == "37.5" and points_text(F(1250)) == "1,250"


def test_commas_are_ignored_and_junk_is_not_a_guess():
    assert parse_guess("28,449") == 28449 and parse_guess("1,234.5") == F("1234.5") and parse_guess(".5") == F(1, 2)
    assert parse_guess("") is None and parse_guess(",") is None and parse_guess("1.2.3") is None
    assert parse_guess("-4") is None


def run_of(level=MEDIUM, seed=7):
    return EstimateRun(MathConfig(mode=ESTIMATE, difficulty=level), seed)


def type_in(run, text):
    for ch in text:
        run.type(ch)


def test_a_timeout_scores_zero_and_moves_on():
    run = run_of()
    first = run.question
    type_in(run, "12")
    run.advance_to(QUESTION_MS - 1)
    assert len(run.rows) == 0 and run.time_left_ms == 1
    run.advance_to(QUESTION_MS)
    assert len(run.rows) == 1 and run.rows[0].guess is None and run.rows[0].points == 0
    assert run.rows[0].question == first and run.rows[0].outcome == "timeout" and run.typed == ""
    run.advance_to(QUESTION_MS * 3 + 500)  # two more ran out while you weren't looking
    assert len(run.rows) == 3 and run.time_left_ms == QUESTION_MS - 500


def test_a_full_run_scores_and_logs():
    run = run_of(HARD, 3)
    total = F(0)
    for i in range(15):
        run.advance_to(run.now + 3_000)
        exact = run.question.exact
        guess = exact * D("1.04") if i % 3 else exact
        type_in(run, f"{guess:,.2f}")
        row = run.submit()
        assert row.ms == 3_000 and row.speed == 2
        total += row.points
    assert run.over and run.points == total and run.count(FULL) + run.count(HALF) == 15
    assert run.count(MISS) == 0 and run.submit() is None
    beaten, last = file_arcade(run)
    assert beaten == ["points"] and F(str(load_bests()["estimate/hard"]["points"])) == total
    rows = load_history()
    assert len(rows) == 15 and {r["family"] for r in rows} == {"est"} and "track" not in rows[0]
    assert load_runs()[-1]["full"] == run.count(FULL) and last[-1]["points"] == load_runs()[-1]["points"]


def test_enter_needs_a_number():
    run = run_of()
    assert run.submit() is None
    type_in(run, ",")
    assert run.submit() is None and len(run.rows) == 0


def test_display_helpers():
    assert two_dp(D("28449")) == "28,449.00" and two_dp(D("24.10394159")) == "24.10"
    assert percent_text(F(1, 100)) == "1.0%" and percent_text(None) == "—"
    assert percent_text(F(10001, 100000)) == "10.1%"  # just over 10% never reads 10.0%
