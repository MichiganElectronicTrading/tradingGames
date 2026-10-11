"""Higher or Lower stage 3: high-score persistence, top-10 trimming, the new-#1 rank, and the review."""

import json
from datetime import date
from fractions import Fraction as F

import pytest

from met_games.games.hilo.config import EASY, FULL, INTERVIEW, MEDIUM
from met_games.games.hilo.engine import OVER, HiloGame, ticks
from met_games.games.hilo.model import GOOD, HIGHER, LOWER, MISS, OK, PERFECT, Card, pct
from met_games.games.hilo.scores import SCORES_FILE, best, record, review_rows, summary, top

C = Card


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MET_GAMES_HOME", str(tmp_path))
    return tmp_path


class Done:
    """A finished game stand-in with a given score."""

    def __init__(self, score, deck=INTERVIEW, mode="EASY", seed=1, multiple=F(3, 2), timed=False):
        self.score, self.seed, self.multiple, self.mode = score, seed, multiple, mode
        self.config = EASY.replace(deck=deck, timed=timed)


def test_scores_persist_per_deck_and_difficulty(isolated_home):
    assert record(Done(500), date(2026, 10, 1)) == 1
    assert record(Done(700, mode="HARD")) == 1  # a different board
    assert record(Done(300, deck=FULL)) == 1
    saved = json.loads((isolated_home / SCORES_FILE).read_text())
    assert set(saved) == {"interview/EASY/untimed", "interview/HARD/untimed", "full/EASY/untimed"}
    assert saved["interview/EASY/untimed"] == [
        {"score": 500, "multiple": 1.5, "date": "2026-10-01", "seed": 1, "timed": False}]
    assert best(INTERVIEW, "EASY")["score"] == 500 and best(FULL, "MEDIUM") is None


def test_top_ten_trimming_and_ranks():
    for s in (100, 900, 500, 300, 700):
        record(Done(s))
    assert [e["score"] for e in top(INTERVIEW, "EASY")] == [900, 700, 500, 300, 100]
    assert record(Done(800)) == 2
    assert record(Done(950)) == 1  # the new-#1 banner case
    assert record(Done(900, seed=9)) == 3  # a tie stays behind the earlier 900
    for s in (10, 20, 30, 40):
        record(Done(s))
    scores = [e["score"] for e in top(INTERVIEW, "EASY")]
    assert len(scores) == 10 and scores == sorted(scores, reverse=True)
    assert record(Done(5)) is None  # doesn't make the top 10
    assert len(top(INTERVIEW, "EASY", 20)) == 10 and top(INTERVIEW, "EASY", 5)[0]["score"] == 950


def test_timed_and_untimed_scores_have_separate_tables(isolated_home):
    assert record(Done(500)) == 1
    assert record(Done(300, timed=True)) == 1  # #1 on its own (timed) table, though below the untimed 500
    assert record(Done(400, timed=True)) == 1
    assert [e["score"] for e in top(INTERVIEW, "EASY")] == [500]
    assert [e["score"] for e in top(INTERVIEW, "EASY", timed=True)] == [400, 300]
    assert best(INTERVIEW, "EASY")["timed"] is False and best(INTERVIEW, "EASY", timed=True)["timed"] is True


def test_tables_saved_before_untimed_play_count_as_timed(isolated_home):
    old = {"interview/EASY": [{"score": 900, "multiple": 2.0, "date": "2026-10-01", "seed": 7}]}
    (isolated_home / SCORES_FILE).write_text(json.dumps(old))
    assert top(INTERVIEW, "EASY") == []
    assert best(INTERVIEW, "EASY", timed=True)["score"] == 900
    assert record(Done(950, timed=True)) == 1
    saved = json.loads((isolated_home / SCORES_FILE).read_text())
    assert set(saved) == {"interview/EASY/timed"} and [e["score"] for e in saved["interview/EASY/timed"]] == [950, 900]


TIMED = EASY.replace(timed=True)


def rigged(cards, cfg=EASY):
    g = HiloGame(cfg.replace(seed=1))
    g.cards = list(cards)
    return g


def test_summary_and_worst_bet():
    g = rigged([C(13, "♠"), C(2, "♥"), C(12, "♦"), C(1, "♣")], TIMED)
    g.lock(LOWER, 100)  # k = 1: PERFECT, LIGHTNING → 200
    g.next_bet()
    g.advance(ticks(6))
    o = g.odds()  # 2 showing, left Q A: h=1 l=1 → k=0, betting = MISS
    g.lock(HIGHER, 50)
    g.next_bet()
    g.lock(LOWER, 100)  # Q showing, left A: k = 1 → PERFECT at combo ×1.0 (streak reset)
    g.next_bet()
    assert g.phase == OVER
    s = summary(g)
    assert s.grades[PERFECT] == 2 and s.grades[MISS] == 1 and s.lightning == 2
    # bet 2 had no edge, so the ideal was a DISCIPLINE sit-out: 50 × NORMAL ×1 × combo ×1.1 = 55
    assert s.worst.number == 2 and s.worst_lost == 55
    rows = review_rows(g)
    assert rows[0][:6] == ("1", "K♠", "0/0/3", "LOWER 100%", "LOWER 100%", PERFECT)
    assert rows[1][3] == "none · 0%" and rows[1][5] == MISS
    assert o.k == 0


def test_worst_bet_counts_speed_and_combo():
    g = rigged([C(13, "♠"), C(1, "♥"), C(13, "♦"), C(12, "♣"), C(2, "♠")], TIMED)
    g.lock(LOWER, 100)  # PERFECT, streak → 1
    g.next_bet()
    g.advance(ticks(3))  # FAST
    g.lock(HIGHER, 10)  # A showing: k = 1 HIGHER; 10% is far off → OK = 20 × 1.1 = 22
    g.next_bet()
    s = summary(g)
    assert g.bets[1].grade == OK and g.bets[1].points == 22
    assert s.worst.number == 2 and s.worst_lost == round(100 * 1.5 * 1.1) - 22  # 165 − 22


def test_benchmark_in_summary_matches_kelly_play():
    g = HiloGame(EASY.replace(seed=4))
    while g.phase != OVER:
        o = g.odds()
        g.lock(o.right, pct(o.k) if o.right else 0)
        g.next_bet()
    assert summary(g).benchmark > 0 and all(b.grade in (PERFECT, GOOD, "DISCIPLINE") for b in g.bets)


def test_review_rows_for_a_timeout_and_sit_out():
    g = HiloGame(MEDIUM.replace(seed=2, timed=True))
    g.advance(ticks(MEDIUM.time_s))
    g.next_bet()
    g.lock(None, 0)
    rows = review_rows(g)
    assert rows[0][4] == "timeout" and rows[1][4] == "sit out"


def test_a_correct_sit_out_is_never_the_worst_bet():
    g = rigged([C(7, "♠"), C(9, "♥"), C(2, "♦"), C(13, "♣")])  # 7 showing: 2 higher (9, K) vs 1 lower → k = 1/3
    g.lock(HIGHER, 33)
    g.next_bet()  # 9 showing, left 2 K: no edge
    g.lock(None, 0)  # DISCIPLINE — the right play
    g.next_bet()
    s = summary(g)
    assert g.bets[1].grade == "DISCIPLINE" and s.worst_lost == 0
