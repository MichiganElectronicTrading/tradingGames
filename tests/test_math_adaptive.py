"""Adaptive difficulty: the track map, every ladder rung, the up/down rule, persistence with daily snapshots,
seeding from history, and a simulated player settling at their level."""

import random
from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_math_problems import recompute, terminates_within

from met_games import storage
from met_games.games.math import adaptive
from met_games.games.math.adaptive import (
    LEVELS_FILE,
    TARGET_MS,
    AdaptiveStream,
    Ladder,
    TrackState,
    load_levels,
    outcome_change,
    save_levels,
    seed_level,
    week_ago,
)
from met_games.games.math.config import ADAPTIVE, SPRINT, SURVIVAL, MathConfig
from met_games.games.math.history import file_run, load_runs
from met_games.games.math.ladder import (
    ANCHORS,
    CEILING,
    DIGITS,
    LEVEL_MAX,
    SUBTYPE_TRACK,
    TRACK_FAMILY,
    TRACKS,
    anchor_of,
    digits,
    make_at,
    track_subtypes,
)
from met_games.games.math.problems import (
    CORE,
    EASY,
    FAMILIES,
    HARD,
    MAX_PLACES,
    MEDIUM,
    SUBTYPE_FAMILY,
    SUBTYPES,
    accepts,
    make,
    within_difficulty,
)
from met_games.games.math.run import CORRECT, new_focus_drill, new_run

N = 2000  # problems per track × level
SIGNED = {"pct_change", "chained", "pnl"}  # answers that may be negative


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


# ── tracks and ladders ──────────────────────────────────────────────────────


def test_every_subtype_maps_to_one_track_of_its_family():
    assert set(SUBTYPE_TRACK) == set(SUBTYPE_FAMILY)
    assert all(TRACK_FAMILY[SUBTYPE_TRACK[s]] == f for s, f in SUBTYPE_FAMILY.items())
    assert set(SUBTYPE_TRACK.values()) == set(TRACKS) and len(TRACKS) == 7
    assert set(TARGET_MS) == set(TRACKS)
    assert TARGET_MS == {"addsub": 2500, "mul": 3000, "div": 3500, "dec": 4500, "frac": 5000, "pct": 5000,
                         "desk": 8000}
    for t in TRACKS:
        for lv in range(1, LEVEL_MAX + 1):
            assert track_subtypes(t, lv), (t, lv)


@pytest.mark.parametrize("level", range(1, LEVEL_MAX + 1))
@pytest.mark.parametrize("track", TRACKS)
def test_every_rung_generates_valid_problems(track, level):
    rng = random.Random(f"{track}-L{level}")
    seen = set()
    for _ in range(N):
        p = make_at(rng, track, level)
        assert p.level == f"L{level}" and SUBTYPE_TRACK[p.subtype] == track and p.family == TRACK_FAMILY[track]
        assert recompute(p) == p.answer, p
        assert terminates_within(p.answer, MAX_PLACES[p.family]), p
        assert accepts(p, p.answer_text), p
        assert p.subtype in SIGNED or p.answer > 0, p
        assert digits(p) <= DIGITS[track][level - 1], p
        if level in CEILING:
            assert within_difficulty(p.steps, CEILING[level]), p
        seen.add(p.subtype)
    assert seen == set(track_subtypes(track, level))


@pytest.mark.parametrize("track", TRACKS)
def test_operand_size_never_drops_and_anchors_are_todays_generators(track):
    reach = DIGITS[track]
    assert list(reach) == sorted(reach) and len(reach) == LEVEL_MAX
    family = TRACK_FAMILY[track]
    for level, anchor in ANCHORS.items():
        subs = [s for s in SUBTYPES[family][anchor] if SUBTYPE_TRACK[s] == track]
        rng = random.Random(f"anchor-{track}-{anchor}")
        top = max(digits(make(rng, family, anchor, rng.choice(subs))) for _ in range(N))
        assert reach[level - 1] == top  # the declared reach is exactly what today's generator reaches
        for sub in subs:
            for seed in range(25):
                ours = make_at(random.Random(seed), track, level, sub)
                theirs = make(random.Random(seed), family, anchor, sub)
                assert ours == replace(theirs, level=f"L{level}")


def test_anchor_of_maps_levels_to_the_nearest_difficulty():
    assert [anchor_of(f"L{n}") for n in range(1, 11)] == [EASY] * 4 + [MEDIUM] * 3 + [HARD] * 3
    assert anchor_of("hard") == "hard" and anchor_of("zetamac") == "zetamac"


# ── the rule ────────────────────────────────────────────────────────────────


def feed(state, answers, target=2500):
    return [outcome_change(state, target, ok, ms) for ok, ms in answers]


def test_three_fast_correct_go_up_and_reset():
    s = TrackState(4)
    assert feed(s, [(True, 2500), (True, 1000), (True, 2400)]) == [0, 0, 1]
    assert (s.level, s.fast, s.slow) == (5, 0, 0)
    assert feed(s, [(True, 100), (True, 100)]) == [0, 0] and s.level == 5  # the counter started again


def test_a_medium_answer_breaks_the_fast_run():
    s = TrackState(4)
    assert feed(s, [(True, 1000), (True, 1000), (True, 2501), (True, 1000), (True, 1000)]) == [0] * 5
    assert s.level == 4 and s.fast == 2
    assert feed(s, [(True, 1000)]) == [1]


def test_a_miss_or_skip_goes_down_at_once():
    s = TrackState(4)
    feed(s, [(True, 1000), (True, 1000)])
    assert feed(s, [(False, 900)]) == [-1] and (s.level, s.fast, s.slow) == (3, 0, 0)


def test_two_slow_correct_in_a_row_go_down():
    s = TrackState(6)
    assert feed(s, [(True, 5001), (True, 5000)]) == [0, 0]  # 2× the target exactly isn't slow: it breaks the run
    assert s.slow == 0
    assert feed(s, [(True, 5001)]) == [0] and s.slow == 1
    assert feed(s, [(True, 9000)]) == [-1] and (s.level, s.slow) == (5, 0)
    assert feed(s, [(True, 9000), (True, 1000), (True, 9000)]) == [0, 0, 0]  # a fast one in between resets


def test_floor_one_and_cap_ten():
    low = TrackState(1)
    assert feed(low, [(False, 0), (True, 9000), (True, 9000)]) == [0, 0, 0] and low.level == 1
    high = TrackState(10)
    assert feed(high, [(True, 1)] * 3) == [0, 0, 0] and (high.level, high.fast) == (10, 0)


def test_the_ladder_keeps_tracks_apart_and_logs_changes():
    lad = Ladder({"mul": 7})
    assert lad.level("mul") == 7 and lad.level("pct") == 3
    for _ in range(3):
        lad.record("addsub", True, 1000)
    lad.record("mul", False, 1000)
    assert lad.levels["addsub"] == 4 and lad.levels["mul"] == 6 and lad.changes == [("addsub", 3, 4), ("mul", 7, 6)]


# ── runs ────────────────────────────────────────────────────────────────────


def answer(run, after_ms):
    run.advance_to(run.now + after_ms)
    for ch in run.problem.answer_text:
        locked = run.type(ch)
    assert locked.outcome == CORRECT
    return locked


def test_an_adaptive_sprint_moves_the_level_mid_run_and_saves_it():
    run = new_run(MathConfig(mode=SPRINT, difficulty=ADAPTIVE, families=(CORE,)), 4, levels={})
    track = SUBTYPE_TRACK[run.problem.subtype]
    assert run.problem.level == "L3"
    while run.ladder.changes == []:
        answer(run, 500)
    assert run.ladder.changes[0][1:] == (3, 4) and run.board == ADAPTIVE
    up = run.ladder.changes[0][0]
    assert sum(SUBTYPE_TRACK[a.problem.subtype] == up for a in run.attempts) == 3
    while SUBTYPE_TRACK[run.problem.subtype] != up:
        answer(run, 500)
    assert run.problem.level == "L4" and track in TRACKS
    run.skip()
    run.end()
    file_run(run)
    saved = storage.read_json(LEVELS_FILE, {})
    assert saved["levels"] == run.ladder.levels and saved["snapshots"][date.today().isoformat()] == run.ladder.levels
    assert load_runs()[-1]["difficulty"] == ADAPTIVE


def test_adaptive_is_sprint_and_survival_only_and_survival_uses_medium_clock():
    run = new_run(MathConfig(mode=SURVIVAL, difficulty=ADAPTIVE), 1, levels={})
    assert run.bonus_ms == 8_000 and run.ladder is not None
    for mode in ("zetamac", "optiver", "chain", "estimate"):
        assert MathConfig(mode=mode, difficulty=ADAPTIVE).errors()
    assert not MathConfig(mode=SPRINT, difficulty=ADAPTIVE).errors()


def test_the_family_toggles_still_choose_the_problems():
    run = new_run(MathConfig(difficulty=ADAPTIVE, families=("pct", "desk")), 9, levels={"desk": 8})
    ps = [run.stream.next() for _ in range(40)]
    assert {p.family for p in ps} == {"pct", "desk"}
    assert all(p.level == ("L8" if p.family == "desk" else "L3") for p in ps)


def test_the_focus_drill_stays_on_its_track():
    run = new_focus_drill(2, "frac", {"frac": 6})
    ps = [run.stream.next() for _ in range(30)]
    assert {SUBTYPE_TRACK[p.subtype] for p in ps} == {"frac"} and run.problem.level == "L6"
    assert run.focus == "frac" and run.board == ADAPTIVE


# ── persistence ─────────────────────────────────────────────────────────────


def test_levels_persist_with_one_snapshot_per_day_kept_60_days():
    start = date(2026, 1, 1)
    for i in range(70):
        save_levels({t: 1 + i % 10 for t in TRACKS}, start + timedelta(days=i))
    save_levels({t: 5 for t in TRACKS}, start + timedelta(days=69))  # a second save that day overwrites
    state = adaptive.load_state()
    days = sorted(state["snapshots"])
    assert len(days) == 60 and days[0] == (start + timedelta(days=10)).isoformat()
    assert state["levels"] == {t: 5 for t in TRACKS} and state["snapshots"][days[-1]] == {t: 5 for t in TRACKS}
    assert load_levels() == {t: 5 for t in TRACKS}


def test_week_ago_is_the_latest_snapshot_at_least_7_days_old():
    today = date(2026, 3, 20)
    assert week_ago(today) is None
    save_levels({t: 4 for t in TRACKS}, today - timedelta(days=3))
    assert week_ago(today) == {t: 4 for t in TRACKS}  # nothing that old yet: the oldest there is
    save_levels({t: 2 for t in TRACKS}, today - timedelta(days=9))
    save_levels({t: 3 for t in TRACKS}, today - timedelta(days=7))
    save_levels({t: 6 for t in TRACKS}, today)
    assert week_ago(today) == {t: 3 for t in TRACKS}
    assert [adaptive.arrow(n, 3) for n in (4, 3, 2)] == ["▲", "·", "▼"] and adaptive.arrow(4, None) == "·"


# ── seeding ─────────────────────────────────────────────────────────────────


def rec(subtype, level, ok):
    return {"subtype": subtype, "level": level, "outcome": "correct" if ok else "skipped", "ms": 1000}


def test_seeding_takes_the_highest_anchor_at_80_percent_over_20():
    history = [rec("mul", HARD, i < 16) for i in range(20)]  # 80% of 20 at HARD
    assert seed_level(history, "mul") == 9
    assert seed_level(history[:19], "mul") == 3  # 19 isn't enough
    history = [rec("add", MEDIUM, i < 17) for i in range(20)] + [rec("sub", HARD, i < 15) for i in range(30)]
    assert seed_level(history, "addsub") == 6  # 50% at HARD doesn't count; 85% at MEDIUM does
    assert seed_level([rec("dec_int", EASY, i < 15) for i in range(20)], "dec") == 3  # 75%: the default anyway
    assert seed_level([rec("vwap", "zetamac", True)] * 40 + [rec("vwap", "L9", True)] * 40, "desk") == 3


def test_first_load_seeds_from_history_once():
    history = [rec("pct_of", MEDIUM, True) for _ in range(25)]
    levels = load_levels(history, date(2026, 5, 1))
    assert levels["pct"] == 6 and all(levels[t] == 3 for t in TRACKS if t != "pct")
    assert load_levels([], date(2026, 5, 2))["pct"] == 6  # saved: history isn't asked again
    assert list(adaptive.load_state()["snapshots"]) == ["2026-05-01"]


# ── a simulated player ──────────────────────────────────────────────────────


def simulate(seed, n=200):
    """A fake player: 95% right and fast up to L5, 40% right above it. Levels after each answer."""
    rng = random.Random(seed)
    lad = Ladder({})
    seen = []
    for _ in range(n):
        right = rng.random() < (0.95 if lad.level("mul") <= 5 else 0.40)
        lad.record("mul", right, 1500 if right else 4000)
        seen.append(lad.level("mul"))
    return seen


def test_a_player_good_to_l5_settles_at_l5_or_l6():
    shares = []
    for seed in range(20):
        seen = simulate(seed)
        assert 5 in seen[:50]  # climbs from L3 quickly
        tail = sorted(seen[-100:])
        assert tail[50] in (5, 6)  # the median over the last 100 problems
        shares.append(sum(lv in (5, 6) for lv in tail))
    assert sum(shares) / len(shares) >= 80  # on average 80%+ of the last 100 at L5–6


def test_an_adaptive_stream_uses_every_family_evenly():
    s = AdaptiveStream(3, {})
    ps = [s.next() for _ in range(40)]
    assert {f: sum(p.family == f for p in ps) for f in FAMILIES} == {f: 10 for f in FAMILIES}
    s1, s2 = AdaptiveStream(5, {}), AdaptiveStream(5, {})
    assert [s1.next() for _ in range(30)] == [s2.next() for _ in range(30)]
