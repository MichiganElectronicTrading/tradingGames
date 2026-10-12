"""The Mental Math daily: the Detroit date, one attempt, the streak, the score card, and the frozen v1 generator."""

import ast
from datetime import date, datetime, timezone
from fractions import Fraction as F
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from met_games.games.math import daily, daily_v1
from met_games.games.math.problems import FAMILIES, MEDIUM

DAY = date(2026, 10, 12)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


# ── the Detroit date ────────────────────────────────────────────────────────


def test_detroit_date_regardless_of_local_timezone():
    la, tokyo = ZoneInfo("America/Los_Angeles"), ZoneInfo("Asia/Tokyo")
    # 23:59 on the 12th in Los Angeles is already 02:59 on the 13th in Detroit
    assert daily.today(datetime(2026, 10, 12, 23, 59, tzinfo=la)) == date(2026, 10, 13)
    # 00:01 on the 13th in Tokyo is still 11:01 on the 12th in Detroit
    assert daily.today(datetime(2026, 10, 13, 0, 1, tzinfo=tokyo)) == date(2026, 10, 12)


def test_day_flips_at_detroit_midnight():
    det = ZoneInfo("America/Detroit")
    assert daily.today(datetime(2026, 10, 12, 23, 59, tzinfo=det).astimezone(timezone.utc)) == date(2026, 10, 12)
    assert daily.today(datetime(2026, 10, 13, 0, 1, tzinfo=det).astimezone(timezone.utc)) == date(2026, 10, 13)
    assert daily.seconds_to_next(datetime(2026, 10, 12, 23, 59, tzinfo=det)) == 60
    assert daily.seconds_to_next(datetime(2026, 11, 1, 0, 0, tzinfo=det)) == 25 * 3600  # DST ends: a 25-hour day


def test_daily_number_counts_from_the_epoch():
    assert daily.number(daily.DAILY_EPOCH) == 1
    assert daily.number(DAY) == (DAY - daily.DAILY_EPOCH).days + 1


# ── one attempt, the streak ─────────────────────────────────────────────────


def test_one_attempt_per_day():
    assert not daily.started(DAY)
    assert daily.start(DAY) is True
    assert daily.started(DAY) and daily.start(DAY) is False
    assert daily.result(DAY) is None
    run = daily.new_daily_run(DAY)
    for _ in range(3):
        for ch in run.problem.answer_text:
            run.type(ch)
    run.skip()
    daily.save_result(DAY, run)
    res = daily.result(DAY)
    assert res["correct"] == 3 and res["skipped"] == 1 and res["points"] == run.points
    assert sum(seen for _, seen in res["families"].values()) == 4


def test_streak_across_days_and_after_a_gap():
    for d in (1, 2, 3, 5, 6):
        daily.start(date(2026, 10, d))
    assert daily.streak(date(2026, 10, 3)) == 3
    assert daily.streak(date(2026, 10, 4)) == 3  # today not played yet: yesterday's streak still stands
    assert daily.streak(date(2026, 10, 6)) == 2  # the gap on the 4th broke it
    assert daily.streak(date(2026, 10, 7)) == 2
    assert daily.streak(date(2026, 10, 8)) == 0


# ── the card ────────────────────────────────────────────────────────────────


def test_card_text_exact():
    res = {"correct": 39, "points": 5480, "best_combo": "11/5",
           "families": {"core": [12, 12], "decfrac": [9, 11], "pct": [8, 10], "desk": [6, 10]}}
    assert daily.daily_card(date(2026, 10, 20), res) == (
        f"MET MATH · daily #{daily.number(date(2026, 10, 20))} · sprint M · v1\n"
        "39 ✓ · 5,480 pts · best ×2.2\n"
        "core ■■■■■   frac ■■■■□\n"
        "%    ■■■■□   desk ■■■□□\n"
        "met-games math --daily"
    )


def test_squares_round_to_fifths_half_up():
    assert [daily.squares(r, 10) for r in (0, 1, 3, 5, 8, 9, 10)] == \
        ["□□□□□", "■□□□□", "■■□□□", "■■■□□", "■■■■□", "■■■■■", "■■■■■"]  # 10% is half a square: rounds up
    assert daily.squares(0, 0) == "□□□□□"


def test_copy_falls_back_without_pbcopy(monkeypatch):
    monkeypatch.setattr(daily.shutil, "which", lambda name: None)
    assert daily.copy("card") is False


# ── the frozen generator ────────────────────────────────────────────────────

SNAPSHOT_2026_10_12 = [
    ("5% of 638", "319/10"),
    ("0.125 as a fraction", "1/8"),
    ("78.35 / 78.42: buy 1000 at the ask, sell at the bid. cost", "70"),
    ("578 + 224", "802"),
    ("147 → 294: % change", "100"),
    ("0.625 as a fraction", "5/8"),
    ("bought 700 @ 84.73, sold @ 83.94: P&L", "-553"),
    ("923 + 935", "1858"),
    ("bought 500 @ 83.21, sold @ 82.72: P&L", "-245"),
    ("7/8 as a decimal", "7/8"),
    ("900 ÷ 9", "100"),
    ("380 → 494: % change", "30"),
    ("notional of 500 @ 53.34", "26670"),
    ("1/4 + 1/2", "3/4"),
    ("851 − 584", "267"),
]


def test_daily_v1_snapshot():
    got = daily_v1.problems(DAY)
    assert len(got) == 200
    assert [(p.text, str(p.answer)) for p in got[:15]] == SNAPSHOT_2026_10_12
    assert all(p.level == MEDIUM for p in got)
    assert {p.family for p in got} == set(FAMILIES)
    assert daily_v1.seed_for(DAY) == "met-math-daily-2026-10-12"


def test_daily_run_is_a_two_minute_medium_sprint_on_the_frozen_problems():
    run = daily.new_daily_run(DAY)
    assert run.time_left_ms == 120_000 and run.board == MEDIUM and run.day == DAY
    assert run.problem.text == "5% of 638" and run.problem.answer == F(319, 10) and run.problem.base == 150


def test_daily_v1_never_imports_the_main_generator():
    tree = ast.parse(Path(daily_v1.__file__).read_text())
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and m.startswith("met_games") for m in modules)
