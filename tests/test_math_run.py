"""Mental Math runs on the millisecond clock: combo and points, Sprint, Survival's bank, Zetamac, Optiver-style."""

from fractions import Fraction as F

import pytest

from met_games.games.math.config import OPTIVER, SPRINT, SURVIVAL, ZETAMAC, MathConfig
from met_games.games.math.optiver import QUESTIONS, optiver_questions
from met_games.games.math.problems import CORE, EASY, HARD, MEDIUM, Problem, parse_answer
from met_games.games.math.run import (
    CORRECT,
    SKIPPED,
    WRONG,
    ListStream,
    OptiverRun,
    Run,
    combo,
    new_run,
    points,
    survival_bonus_ms,
)


def answer(run, at_ms=None):
    """Type the current answer, one key at a time."""
    if at_ms is not None:
        run.advance_to(at_ms)
    text = run.problem.answer_text
    locked = None
    for ch in text:
        locked = run.type(ch)
    assert locked is not None and locked.outcome == CORRECT
    return locked


def fixed(n=500, base_answer=7):
    return ListStream(Problem(f"{i} + 0", F(i + base_answer), CORE, "add", MEDIUM, "add", (i, 0)) for i in range(n))


# ── combo and points ────────────────────────────────────────────────────────


def test_combo_and_points_math():
    assert combo(0) == 1 and combo(1) == F(11, 10) and combo(12) == F(22, 10) and combo(20) == 3 and combo(50) == 3
    assert points(100, 0) == 100 and points(150, 3) == 195 and points(200, 25) == 600


def test_points_use_the_pre_answer_streak_and_skip_resets():
    r = Run(SPRINT, fixed(), duration_ms=120_000, board=MEDIUM, seed=1)
    a = [answer(r, 1000 * i) for i in range(1, 4)]
    assert [x.points for x in a] == [100, 110, 120] and [x.streak_before for x in a] == [0, 1, 2]
    assert r.streak == 3 and r.best_combo == F(12, 10)
    s = r.skip()
    assert s.outcome == SKIPPED and s.points == 0 and r.streak == 0
    assert answer(r).points == 100
    for _ in range(30):
        answer(r)
    assert r.attempts[-1].points == 300 and r.best_combo == 3  # capped
    assert r.points == sum(x.points for x in r.attempts) and r.correct == 34 and r.skipped == 1


def test_typing_locks_only_on_the_exact_answer_and_backspace_works():
    r = Run(SPRINT, fixed(base_answer=120), duration_ms=120_000, board=MEDIUM, seed=1)  # answer 120
    assert r.type("1") is None and r.type("3") is None and r.typed == "13"
    r.backspace()
    assert r.type("x") is None and r.typed == "1"
    assert r.type("2") is None
    assert r.type("0").outcome == CORRECT and r.typed == ""


def test_sprint_times_out_and_the_open_problem_isnt_scored():
    r = new_run(MathConfig(mode=SPRINT, duration_s=30), seed=4)
    answer(r, 2_000)
    r.advance_to(29_999)
    assert not r.over and r.time_left_ms == 1
    shown = r.problem
    r.advance_to(30_000)
    assert r.over and len(r.attempts) == 1 and r.problem is shown
    assert r.type("1") is None and r.skip() is None


def test_time_to_answer_is_from_when_the_problem_showed():
    r = Run(SPRINT, fixed(), duration_ms=120_000, board=MEDIUM, seed=1)
    assert answer(r, 2_500).ms == 2_500
    assert answer(r, 3_700).ms == 1_200
    r.advance_to(5_000)
    assert r.skip().ms == 1_300


# ── Survival ────────────────────────────────────────────────────────────────


def test_survival_bonus_decay_schedule_and_floor():
    assert [survival_bonus_ms(n, 8000, 1000) for n in (0, 4, 5, 9, 10, 65, 69, 70, 500)] == \
        [8000, 8000, 7500, 7500, 7000, 1500, 1500, 1000, 1000]


@pytest.mark.parametrize("difficulty, start, at_floor", [(EASY, 10_000, 90), (MEDIUM, 8_000, 70),
                                                         (HARD, 6_000, 50)])
def test_survival_bonus_by_difficulty_drops_every_5_correct_to_1s(difficulty, start, at_floor):
    r = Run(SURVIVAL, fixed(), duration_ms=0, board=difficulty, seed=1,
            config=MathConfig(mode=SURVIVAL, difficulty=difficulty))
    assert r.time_left_ms == 30_000 and r.bonus_ms == start and r.bonus_floor_ms == 1_000
    bonuses = {}
    while r.correct < at_floor + 30:
        bonuses[r.correct] = r.bonus_ms
        bank = r.bank_ms
        r.advance_to(r.now + 1)  # the run's (fake) millisecond clock
        answer(r)
        assert r.bank_ms - bank == bonuses[r.correct - 1]  # that bonus is what the answer added
        if r.correct % 7 == 0:  # skips don't count toward the 5
            before = r.bonus_ms
            r.skip()
            assert r.bonus_ms == before
    assert (bonuses[0], bonuses[5], bonuses[10]) == (start, start - 500, start - 1_000)  # e.g. 10 → 9.5 → 9
    assert bonuses[at_floor - 1] == 1_500 and bonuses[at_floor] == 1_000  # reaches 1s exactly there
    assert all(b == 1_000 for n, b in bonuses.items() if n >= at_floor)  # and stays
    assert min(bonuses.values()) == 1_000  # never below


def test_survival_clock_bonuses_skip_penalty_and_game_over():
    r = Run(SURVIVAL, fixed(), duration_ms=0, board=MEDIUM, seed=1)  # no config: MEDIUM's +8s
    assert r.time_left_ms == 30_000 and r.bonus_ms == 8000
    answer(r, 1_000)
    assert r.time_left_ms == 37_000  # 30 − 1 + 8
    r.skip()
    assert r.time_left_ms == 32_000 and r.streak == 0
    r.advance_to(r.now + r.time_left_ms - 1)
    assert not r.over
    r.advance_to(r.now + 1)
    assert r.over and r.time_left_ms == 0


def test_custom_survival_bonus_with_the_fixed_1s_floor():
    cfg = MathConfig(mode=SURVIVAL, difficulty="custom", bonus_ms=12_000)
    assert cfg.survival_bonus() == (12_000, 1_000) and cfg.errors() == []
    assert MathConfig(mode=SURVIVAL, difficulty="custom").survival_bonus() == (8_000, 1_000)
    assert MathConfig(mode=SURVIVAL, difficulty=HARD, bonus_ms=12_000).survival_bonus() == (6_000, 1_000)
    assert MathConfig(difficulty="custom", bonus_ms=25_000).errors() == ["survival bonus must be 1–20s"]
    r = Run(SURVIVAL, fixed(), duration_ms=0, board="custom", seed=1, config=cfg)
    for _ in range(300):
        r.advance_to(r.now + 1)
        answer(r)
    assert r.bonus_ms == 1_000


def test_survival_skip_can_end_it():
    r = Run(SURVIVAL, fixed(), duration_ms=0, board=MEDIUM, seed=1)
    r.advance_to(26_000)
    r.skip()
    assert r.over and r.time_left_ms == 0


# ── Zetamac ─────────────────────────────────────────────────────────────────


def test_zetamac_is_120s_raw_score_no_points():
    r = new_run(MathConfig(mode=ZETAMAC), seed=3)
    assert r.time_left_ms == 120_000 and r.board == "standard"
    for i in range(5):
        answer(r, 1000 * (i + 1))
    assert r.correct == 5 and r.points == 0
    r.advance_to(120_000)
    assert r.over


# ── Optiver-style ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", [1, 2, 3, 99, 2026])
def test_optiver_questions_have_one_right_and_four_distinct_options(seed):
    qs = optiver_questions(seed)
    assert len(qs) == QUESTIONS
    for q in qs:
        assert len(q.options) == 4 and len(set(q.options)) == 4
        values = [parse_answer(o) for o in q.options]
        assert len(set(values)) == 4  # distinct values too, not just spellings
        assert values[q.correct] == q.problem.answer
        assert sum(v == q.problem.answer for v in values) == 1
        assert q.problem.family in ("decfrac", "pct", "core") and q.problem.level in ("medium", "hard")
    assert optiver_questions(seed) == qs
    assert len({q.correct for q in qs}) == 4  # the right answer moves around


def test_optiver_scoring_and_no_going_back():
    r = new_run(MathConfig(mode=OPTIVER), seed=5)
    assert isinstance(r, OptiverRun) and r.time_left_ms == 480_000
    first = r.question
    r.advance_to(4_000)
    a = r.answer(first.correct)
    assert a.outcome == CORRECT and a.ms == 4_000 and r.question is not first
    r.advance_to(10_000)
    b = r.answer((r.question.correct + 1) % 4)
    assert b.outcome == WRONG and b.ms == 6_000
    assert r.skip().outcome == SKIPPED
    assert (r.correct, r.wrong, r.skipped, r.net, r.answered) == (1, 1, 1, 0, 3)
    assert r.i == 3 and not hasattr(r, "back")
    avg, need = r.pace()
    assert avg == F(10, 3) and need == F(470, 77)
    while not r.over:
        r.answer(r.question.correct)
    assert r.answered == 80 and r.net == 77 and r.answer(0) is None


def test_optiver_ends_at_eight_minutes():
    r = OptiverRun(1)
    r.advance_to(480_000)
    assert r.over and r.answer(0) is None
