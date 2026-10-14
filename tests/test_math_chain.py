"""Chain: the carry stays a whole number in range with exact links, the step clock, breaking, HARD's hidden carry,
points and combo, Custom, and what gets logged."""

from fractions import Fraction as F

import pytest

from met_games.games.math.chain import (
    RULES,
    TIMEOUT,
    WRONG,
    ChainRun,
    Link,
    apply,
    next_link,
    rules_for,
)
from met_games.games.math.config import CHAIN, CUSTOM, DIVIDE, PERCENT, PM, TIMES, MathConfig
from met_games.games.math.history import file_arcade, load_bests, load_history, load_runs
from met_games.games.math.problems import EASY, HARD, MEDIUM
from met_games.games.math.tips import render


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


def chain(difficulty=MEDIUM, seed=1, **kw):
    return ChainRun(MathConfig(mode=CHAIN, difficulty=difficulty, **kw), seed)


def solve(run, after_ms=1000):
    run.advance_to(run.now + after_ms)
    for ch in str(run.link.answer):
        run.type(ch)
    return run.submit()


def exact(link: Link) -> F:
    c, n = F(link.carry), F(link.operand)
    return {"+": c + n, "−": c - n, "×": c * n, "÷": c / n, "+%": c * (1 + n / 100), "−%": c * (1 - n / 100)}[link.op]


@pytest.mark.parametrize("difficulty", [EASY, MEDIUM, HARD])
def test_the_carry_stays_a_positive_whole_number_in_range(difficulty):
    rules = RULES[difficulty]
    seen = set()
    for seed in range(40):
        run = chain(difficulty, seed)
        assert rules.start[0] <= run.start <= rules.start[1]
        for _ in range(150):
            link = run.link
            assert exact(link) == link.answer and F(link.answer).denominator == 1
            assert 1 <= link.answer <= rules.max_carry and 1 <= link.carry <= rules.max_carry
            if link.op in "+−":
                assert 1 <= link.operand <= 99
            elif link.op == "×":
                assert 2 <= link.operand <= rules.mul_max
            elif link.op == "÷":
                assert 2 <= link.operand <= rules.div_max and link.carry % link.operand == 0
            else:
                assert link.operand in rules.percents
            seen.add(link.kind)
            done = solve(run)
            assert done.outcome == "correct" and run.carry == link.answer
    assert seen == ({PM, TIMES, DIVIDE} if difficulty == EASY else {PM, TIMES, DIVIDE, PERCENT})


def test_limits_per_difficulty():
    assert (RULES[EASY].max_carry, RULES[EASY].step_ms, RULES[EASY].mul_max, RULES[EASY].percents) == \
        (999, 15_000, 9, ())
    assert (RULES[MEDIUM].max_carry, RULES[MEDIUM].step_ms, RULES[MEDIUM].mul_max, RULES[MEDIUM].percents) == \
        (9_999, 12_000, 12, (10, 20, 25, 50))
    assert (RULES[HARD].max_carry, RULES[HARD].step_ms, RULES[HARD].div_max, len(RULES[HARD].percents)) == \
        (9_999, 10_000, 19, 99)


def test_the_generator_rerolls_instead_of_clamping():
    import random

    rules = RULES[EASY]
    for carry in (1, 2, 997, 999):
        for seed in range(200):
            link = next_link(random.Random(seed), carry, rules)
            assert 1 <= link.answer <= 999 and apply(carry, link.op, link.operand) == link.answer
    assert apply(7, "÷", 2) is None and apply(30, "+%", 25) is None and apply(40, "−%", 25) == 30


def test_the_step_clock_times_out_and_resets_each_link():
    run = chain(EASY, 3)
    run.advance_to(14_999)
    assert not run.over and run.time_left_ms == 1
    for ch in str(run.link.answer):
        run.type(ch)
    run.submit()
    assert run.time_left_ms == 15_000 and run.length == 1
    run.advance_to(14_999 + 14_999)
    assert not run.over
    run.type("1")
    run.advance_to(14_999 + 15_000)
    assert run.over and run.broke.outcome == TIMEOUT and run.broke.given == "" and run.length == 1
    assert run.broke.link.carry == run.links[-1].link.answer


def test_a_wrong_answer_ends_the_chain():
    run = chain(MEDIUM, 5)
    solve(run)
    solve(run)
    right = run.link.answer
    for ch in str(right + 1):
        run.type(ch)
    assert run.submit().outcome == WRONG
    assert run.over and run.broke.given == str(right + 1) and run.length == 2
    assert run.submit() is None  # nothing more once it's over


def test_enter_with_nothing_typed_does_nothing_and_backspace_erases():
    run = chain(EASY, 2)
    assert run.submit() is None and not run.over
    run.type("9")
    run.type("x")
    run.backspace()
    assert run.typed == ""


def test_hard_hides_the_carry_after_the_first_answer():
    run = chain(HARD, 4)
    assert not run.hidden and run.shown == run.link.text and run.shown.startswith(str(run.start))
    solve(run)
    assert run.hidden and run.shown == f"? {run.link.op_text}" and str(run.carry) not in run.shown.split()[0]
    easy = chain(EASY, 4)
    solve(easy)
    assert not easy.hidden and easy.shown == f"{easy.carry} {easy.link.op_text}"


def test_points_and_combo():
    run = chain(MEDIUM, 8)
    expected = []
    for i in range(25):
        base = 150 if run.link.kind == PERCENT else 100
        expected.append(round(base * min(1 + F(i, 10), 3)))
        assert solve(run).points == expected[-1]
    assert run.points == sum(expected) and run.combo == 3 and run.best_combo == 3
    assert [d.points for d in run.links][:3] == [round((150 if d.link.kind == PERCENT else 100) * (1 + F(i, 10)))
                                                 for i, d in enumerate(run.links[:3])]


def test_custom_step_clock_and_toggles():
    cfg = MathConfig(mode=CHAIN, difficulty=CUSTOM, step_s=6, ops=(PM, DIVIDE))
    rules = rules_for(cfg)
    assert rules.step_ms == 6_000 and rules.kinds == (PM, DIVIDE) and rules.max_carry == 9_999
    for seed in range(20):
        run = ChainRun(cfg, seed)
        for _ in range(60):
            assert run.link.kind in (PM, DIVIDE)
            solve(run, 500)
    run = ChainRun(cfg, 0)
    run.advance_to(6_000)
    assert run.over
    assert MathConfig(mode=CHAIN, difficulty=CUSTOM, ops=(TIMES,)).errors()  # ± stays on
    assert MathConfig(mode=CHAIN, difficulty=CUSTOM, step_s=21).errors()
    assert MathConfig(mode=CHAIN, difficulty="adaptive").errors()


def test_links_are_logged_with_tracks_and_bests_filed():
    run = chain(MEDIUM, 6)
    for _ in range(4):
        solve(run, 2000)
    run.advance_to(run.now + 12_000)
    beaten, last = file_arcade(run)
    assert beaten == ["length", "points"] and load_bests()["chain/medium"]["length"] == 4
    rows = load_history()
    assert [r["outcome"] for r in rows] == ["correct"] * 4 + ["timeout"]
    assert all(r["mode"] == CHAIN and r["track"] in ("addsub", "mul", "div", "pct") for r in rows)
    assert {r["subtype"] for r in rows} <= {"chain_add", "chain_sub", "chain_mul", "chain_div", "chain_pct"}
    assert load_runs()[-1]["length"] == 4 and load_runs()[-1]["broke"] == TIMEOUT and last[-1]["length"] == 4


def test_every_link_has_a_tip():
    run = chain(HARD, 11)
    for _ in range(80):
        p = run.link.problem()
        title, rule, example = render(p.tip_key, p)
        assert title and rule and example
        solve(run)
