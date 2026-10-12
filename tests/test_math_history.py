"""Mental Math history, "your usual", the weakness report, slowest 3, tips, the drill, and bests."""

import random
from datetime import datetime
from fractions import Fraction as F

import pytest

from met_games import storage
from met_games.games.math.config import DRILL, SPRINT, ZETAMAC, MathConfig
from met_games.games.math.history import (
    HISTORY_FILE,
    RUNS_FILE,
    build_report,
    drill_pool,
    lifetime,
    load_bests,
    load_history,
    load_runs,
    log_run,
    record_bests,
    slowest,
    subtype_rows,
    usual_ms,
    vs_usual,
    weakest,
)
from met_games.games.math.problems import CORE, DESK, FAMILIES, LEVELS, MEDIUM, PCT, Problem, make
from met_games.games.math.run import CORRECT, SKIPPED, Attempt, ListStream, Run, new_run
from met_games.games.math.tips import SUBTYPE_TIPS, TIPS, render

WHEN = datetime(2026, 10, 12, 9, 30)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def p(sub="mul", family=CORE, ops=(36, 25), ans=900, tip="mul_25"):
    return Problem(f"{ops[0]} × {ops[1]}", F(ans), family, sub, MEDIUM, tip, ops)


def att(problem, ms, outcome=CORRECT):
    return Attempt(problem, outcome, ms, 0, 0)


def hist(sub, times):
    return [{"subtype": sub, "outcome": CORRECT, "ms": t} for t in times]


def play(run, script):
    """script: list of (ms_after_previous, 'a' answer | 's' skip)."""
    for gap, what in script:
        run.advance_to(run.now + gap)
        if what == "s":
            run.skip()
        else:
            for ch in run.problem.answer_text:
                run.type(ch)


def test_every_problem_shown_is_logged(isolated_home):
    r = new_run(MathConfig(mode=SPRINT), seed=7)
    play(r, [(2000, "a"), (3000, "s"), (1500, "a")])
    log_run(r, WHEN)
    rows = load_history()
    assert len(rows) == 3
    assert [x["outcome"] for x in rows] == ["correct", "skipped", "correct"]
    assert [x["ms"] for x in rows] == [2000, 3000, 1500]
    for x, a in zip(rows, r.attempts):
        assert x["date"] == "2026-10-12" and x["mode"] == SPRINT and x["difficulty"] == MEDIUM
        assert (x["family"], x["subtype"], x["level"]) == (a.problem.family, a.problem.subtype, a.problem.level)
    runs = load_runs()
    assert len(runs) == 1 and runs[0]["correct"] == 2 and runs[0]["skipped"] == 1 and runs[0]["seed"] == 7
    assert (isolated_home / HISTORY_FILE).exists() and (isolated_home / RUNS_FILE).exists()


def test_usual_is_the_median_of_the_last_200_with_at_least_10_samples():
    assert usual_ms(hist("mul", [1000] * 9), "mul") is None
    assert usual_ms(hist("mul", [1000] * 9 + [3000]), "mul") == 1000
    assert usual_ms(hist("mul", [1000, 2000, 3000, 4000] * 3), "mul") == 2500  # even count: mean of the middle two
    old = hist("mul", [9000] * 300)
    assert usual_ms(old + hist("mul", [2000] * 200), "mul") == 2000  # only the last 200 count
    mixed = hist("mul", [2000] * 10) + hist("add", [500] * 50) + [{"subtype": "mul", "outcome": SKIPPED, "ms": 1}] * 50
    assert usual_ms(mixed, "mul") == 2000  # other subtypes and skips don't count


def test_faster_slower_same_thresholds():
    assert vs_usual(F(2290), F(2000)) == ("same", F(29, 100))
    assert vs_usual(F(2300), F(2000)) == ("slower by 0.3s", F(3, 10))
    assert vs_usual(F(1200), F(2000)) == ("faster by 0.8s", F(-4, 5))
    assert vs_usual(F(1710), F(2000))[0] == "same"
    assert vs_usual(None, F(2000)) == ("—", None) and vs_usual(F(1000), None) == ("—", None)


def test_rows_and_weakest_two_by_accuracy_then_slower_than_usual():
    mul, add, pnl, pc = p(), p("add", ops=(2, 3), ans=5, tip="add"), p("pnl", DESK), p("pct_of", PCT)
    attempts = [
        att(mul, 3000), att(mul, 5000), att(mul, 1000, SKIPPED),  # 2/3
        att(add, 1000), att(add, 1000),  # 2/2
        att(pnl, 9000), att(pnl, 1000, SKIPPED),  # 1/2
        att(pc, 4000), att(pc, 4000), att(pc, 2000, SKIPPED),  # 2/3, slower vs usual than mul
    ]
    history = hist("mul", [4000] * 10) + hist("pct_of", [2000] * 10)
    rows = subtype_rows(attempts, history)
    assert [r.subtype for r in rows] == ["add", "mul", "pct_of", "pnl"]  # family order
    by = {r.subtype: r for r in rows}
    assert (by["mul"].seen, by["mul"].right, by["mul"].avg_ms, by["mul"].usual_ms) == (3, 2, 4000, 4000)
    assert by["mul"].vs == "same" and by["pct_of"].vs == "slower by 2.0s" and by["pnl"].vs == "—"
    assert [r.subtype for r in weakest(rows)] == ["pnl", "pct_of"]
    assert drill_pool(rows) == [(DESK, "pnl"), (PCT, "pct_of")]


def test_slowest_three():
    a = [att(p(), ms) for ms in (1000, 7000, 3000, 9000, 5000)]
    assert [x.ms for x in slowest(a)] == [9000, 7000, 5000]


def test_report_has_the_shortcut_for_the_slowest_problem_with_its_numbers():
    r = Run(SPRINT, ListStream([p(), p("add", ops=(47, 38), ans=85, tip="add")]), duration_ms=120_000, board=MEDIUM,
            seed=1)
    play(r, [(4000, "a"), (1000, "a")])
    rep = build_report(r, [], [{"mode": SPRINT, "difficulty": MEDIUM, "correct": c} for c in range(7)])
    title, rule, example = rep.shortcut
    assert title == "×25" and rule == "×25 = ×100 ÷ 4." and example == "36 × 25 = 36 × 100 ÷ 4 = 3,600 ÷ 4 = 900"
    assert [x["correct"] for x in rep.last_runs] == [2, 3, 4, 5, 6]
    assert rep.avg_ms == 2500


def test_tips_cover_every_subtype_and_render_with_real_numbers():
    assert {k for keys in SUBTYPE_TIPS.values() for k in keys} == set(TIPS)
    rng = random.Random(3)
    seen = set()
    for family in FAMILIES:
        for level in LEVELS:
            for _ in range(300):
                prob = make(rng, family, level)
                assert prob.tip_key in SUBTYPE_TIPS[prob.subtype]
                title, rule, example = render(prob.tip_key, prob)
                assert title and rule and example
                tail = example.replace(",", "").replace("−", "-").split("=")[-1].split("(")[0].strip().rstrip("%")
                assert F(tail) == prob.answer, (prob.text, example)
                seen.add(prob.tip_key)
    assert seen == set(TIPS)
    assert render("vwap") == ("VWAP", TIPS["vwap"].rule, None)


def test_named_tips():
    vwap = Problem("VWAP of 200 @ 42.10, 300 @ 42.20", F("42.16"), DESK, "vwap", "hard", "vwap",
                   ((200, F("42.10")), (300, F("42.20"))))
    assert render("vwap", vwap)[2] == "42.10 + 0.10 × 300/500 = 42.10 + 0.06 = 42.16"
    same = Problem("up 20% then down 20%: net %", F(-4), PCT, "chained", "hard", "chained_same", (20, -20))
    assert render("chained_same", same)[2] == "up and down 20%: net −20² ÷ 100 = −4%"
    eighth = Problem("3/8 as a decimal", F(3, 8), "decfrac", "frac_dec", MEDIUM, "eighths", (F(3, 8),), "decimal")
    assert render("eighths", eighth) == ("The 1/8 family", "1/8 = 0.125: 3/8 = 0.375, 5/8 = 0.625, 7/8 = 0.875.",
                                         "3/8 = 3 × 0.125 = 0.375")
    change = Problem("80 → 92: % change", F(15), PCT, "pct_change", MEDIUM, "pct_change", (80, 92))
    assert render("pct_change", change)[2] == "(92 − 80) ÷ 80 = 0.15 = 15%"


def test_drill_uses_only_the_two_weakest_subtypes_and_never_counts_for_bests():
    pool = [(CORE, "mul"), (PCT, "pct_change")]
    r = new_run(MathConfig(mode=DRILL), seed=4, pool=pool)
    assert r.mode == DRILL and r.time_left_ms == 120_000
    play(r, [(1000, "a")] * 30)
    assert {(a.problem.family, a.problem.subtype) for a in r.attempts} == set(pool)
    assert record_bests(r) == [] and load_bests() == {}
    log_run(r, WHEN)
    assert len(load_history()) == 30 and load_runs()[0]["mode"] == DRILL


def test_bests_per_mode_and_difficulty():
    r = new_run(MathConfig(mode=SPRINT), seed=1)
    play(r, [(1000, "a")] * 5)
    assert record_bests(r, WHEN) == ["correct", "points"]
    worse = new_run(MathConfig(mode=SPRINT), seed=2)
    play(worse, [(1000, "a")] * 4)
    assert record_bests(worse, WHEN) == []
    more_points = new_run(MathConfig(mode=SPRINT), seed=3)
    play(more_points, [(1000, "a")] * 5)
    beat = record_bests(more_points, WHEN)
    assert ("correct" not in beat) and (beat == ["points"]) == (more_points.points > r.points)
    z = new_run(MathConfig(mode=ZETAMAC), seed=1)
    play(z, [(1000, "a")] * 3)
    assert record_bests(z, WHEN) == ["raw"]
    bests = load_bests()
    assert bests["sprint/medium"]["correct"] == 5 and bests["zetamac/standard"] == {"raw": 3, "raw_date": "2026-10-12"}
    easy = new_run(MathConfig(mode=SPRINT, difficulty="easy"), seed=1)
    play(easy, [(1000, "a")])
    assert record_bests(easy, WHEN) == ["correct", "points"]  # its own board


def test_lifetime_stats():
    history = hist("mul", [1000, 3000]) + [{"subtype": "mul", "outcome": SKIPPED, "ms": 5}] + hist("vwap", [4000])
    assert lifetime(history) == [("mul", 3, 2, 2000), ("vwap", 1, 1, 4000)]
    assert storage.read_jsonl(HISTORY_FILE) == []


def test_drill_pool_keeps_each_subtype_at_the_difficulty_it_was_seen_at():
    from met_games.games.math.run import new_drill

    hard = Problem("x", F(1), CORE, "mul", "hard", "mul_split", (2, 3))
    zet = Problem("y", F(1), CORE, "add", "zetamac", "add", (2, 3))
    attempts = [att(hard, 1000, SKIPPED), att(zet, 1000, SKIPPED)]
    pool = drill_pool(subtype_rows(attempts, []), attempts)
    assert sorted(pool) == [(CORE, "add", MEDIUM), (CORE, "mul", "hard")]
    r = new_drill(3, pool, "zetamac")
    levels = {(a.problem.subtype, a.problem.level) for a in (r.skip() for _ in range(20))}
    assert levels == {("add", MEDIUM), ("mul", "hard")}
