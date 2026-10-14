"""MY STATS aggregation: the sparkline, first-10 vs last-10 medians, 7-day arrows, focus next, bests at their best
difficulty, and the focus drill staying out of the bests."""

from datetime import date, timedelta
from fractions import Fraction as F

import pytest

from met_games.games.math.adaptive import save_levels, week_ago
from met_games.games.math.history import record_bests
from met_games.games.math.ladder import TRACKS
from met_games.games.math.progress import (
    best_rows,
    best_value,
    family_split,
    focus_next,
    header,
    level_rows,
    primary,
    recent,
    sparkline,
    trend,
)
from met_games.games.math.run import CORRECT, new_focus_drill


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def test_sparkline_scales_to_its_own_min_and_max():
    assert sparkline([0, 7]) == "▁█"
    assert sparkline([10, 11, 12, 13, 14, 15, 16, 17]) == "▁▂▃▄▅▆▇█"
    assert sparkline([100, 150, 200]) == "▁▅█"  # 3.5 rounds half up
    assert sparkline([5, 5, 5]) == "▄▄▄"  # all equal: a flat middle line
    assert sparkline([F("37.5"), 40.0]) == "▁█" and sparkline([]) == ""


def test_trend_and_primary_stat_per_mode():
    assert trend([F(3), F(9), F(1), F(5)]) == (3, 4, 5) and trend([]) is None
    runs = [{"mode": "sprint", "difficulty": "medium", "correct": n} for n in range(30)]
    runs += [{"mode": "optiver", "difficulty": "standard", "correct": 50, "wrong": 7},
             {"mode": "chain", "difficulty": "hard", "length": 12, "correct": 12},
             {"mode": "estimate", "difficulty": "easy", "points": 1237.5}]
    assert recent(runs, "sprint", "medium") == list(range(10, 30))
    assert [primary(r) for r in runs[-3:]] == [43, 12, F("1237.5")]


def hist(n_runs, family="core", ms=lambda i: 1000 + i):
    out = []
    for i in range(n_runs):
        out.append({"run": f"r{i}", "family": family, "outcome": CORRECT, "ms": ms(i), "subtype": "add"})
        out.append({"run": f"r{i}", "family": family, "outcome": "skipped", "ms": 1, "subtype": "add"})
    return out


def test_first_10_vs_last_10_medians_need_20_runs():
    assert family_split(hist(19)) is None
    split = family_split(hist(20, ms=lambda i: 3000 if i < 10 else 2000))
    assert split["core"] == (3000, 2000) and split["desk"] == (None, None)
    h = hist(25, ms=lambda i: 1000 * i)  # first 10: 0…9 s · last 10: 15…24 s
    assert family_split(h)["core"] == (4500, 19500)


def test_7_day_arrows():
    today = date(2026, 6, 15)
    save_levels({t: 5 for t in TRACKS}, today - timedelta(days=8))
    now = {**{t: 5 for t in TRACKS}, "mul": 7, "pct": 3}
    save_levels(now, today)
    rows = dict((t, (lv, a)) for t, lv, a in level_rows(now, week_ago(today)))
    assert rows["mul"] == (7, "▲") and rows["pct"] == (3, "▼") and rows["addsub"] == (5, "·")
    assert [a for _, _, a in level_rows(None, None)] == ["·"] * 7


def test_focus_next_is_the_biggest_drop_else_the_lowest_accuracy():
    week = {t: 5 for t in TRACKS}
    levels = {**week, "div": 4, "frac": 2, "desk": 2}
    assert focus_next(levels, week, []) == ("frac", "down 3 levels in 7 days")  # ties: the first track
    history = ([{"subtype": "vwap", "outcome": CORRECT}] * 3 + [{"subtype": "pct_of", "outcome": "skipped"}]
               + [{"subtype": "pct_of", "outcome": CORRECT}] + [{"track": "mul", "subtype": "chain_mul",
                                                                  "outcome": CORRECT}])
    assert focus_next(week, week, history) == ("pct", "50% right over your last 100 problems")
    assert focus_next({**week, "mul": 6}, week, history)[0] == "pct"  # going up isn't a drop
    old = [{"subtype": "add", "outcome": "skipped"}] * 50  # beyond the last 100: forgotten
    assert focus_next(None, None, old + [{"subtype": "mul", "outcome": CORRECT}] * 100) == \
        ("mul", "100% right over your last 100 problems")
    assert focus_next(None, None, [{"family": "est", "subtype": "est_mul", "outcome": "full"}]) is None


def test_bests_at_the_hardest_difficulty_with_a_best():
    bests = {"sprint/easy": {"correct": 40, "correct_date": "2026-01-02"},
             "sprint/hard": {"correct": 12, "correct_date": "2026-03-04", "points": 1500},
             "chain/medium": {"length": 9, "length_date": "2026-02-02"}}
    rows = {m: (d, e) for m, d, e in best_rows(bests)}
    assert rows["sprint"][0] == "hard" and best_value("sprint", rows["sprint"][1]) == ("correct", 12, "2026-03-04")
    assert rows["chain"][0] == "medium" and rows["estimate"] == (None, {})
    assert header([{"date": "2026-02-01"}, {"date": "2026-01-15"}]) == (2, "2026-01-15") and header([]) == (0, None)


def test_the_focus_drill_never_counts_toward_bests():
    run = new_focus_drill(1, "mul", {"mul": 4})
    for _ in range(5):
        for ch in run.problem.answer_text:
            run.type(ch)
    assert run.correct == 5 and record_bests(run) == []
