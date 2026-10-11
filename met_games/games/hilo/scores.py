"""Higher or Lower high scores (~/.met_games/hilo_scores.json) and the end-of-game review. Pure Python."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction
from typing import Any

from met_games import storage
from met_games.games.hilo.engine import HiloGame
from met_games.games.hilo.model import (
    DISCIPLINE,
    FAST,
    LIGHTNING,
    PERFECT,
    SPEED,
    STREAK_GRADES,
    benchmark,
    combo_multiplier,
    pct,
    points,
)

SCORES_FILE = "hilo_scores.json"
HISTORY_FILE = "hilo_history.jsonl"
TOP = 10
GRADES = ("PERFECT", "GOOD", "OK", "DISCIPLINE", "SAT OUT", "MISS")


def key(deck: str, mode: str, timed: bool = False) -> str:
    """Timed and untimed scores aren't comparable, so each has its own table."""
    return f"{deck}/{mode}/{'timed' if timed else 'untimed'}"


def load() -> dict[str, list[dict[str, Any]]]:
    data = storage.read_json(SCORES_FILE, {})
    if not isinstance(data, dict):
        return {}
    # Tables saved before untimed play existed ("deck/mode") were all timed.
    for old in [k for k in data if k.count("/") == 1]:
        entries = [{**e, "timed": True} for e in data.pop(old)]
        data.setdefault(f"{old}/timed", entries)
    return data


def top(deck: str, mode: str, n: int = TOP, timed: bool = False) -> list[dict[str, Any]]:
    return load().get(key(deck, mode, timed), [])[:n]


def best(deck: str, mode: str, timed: bool = False) -> dict[str, Any] | None:
    entries = top(deck, mode, 1, timed)
    return entries[0] if entries else None


def record(game: HiloGame, when: date | None = None) -> int | None:
    """Add a finished game to its (deck, difficulty) top 10. Returns its rank (1 = a new high score), or None
    if it didn't make the list. Ties keep the earlier score ahead."""
    data = load()
    k = key(game.config.deck, game.mode, game.config.timed)
    entries = data.get(k, [])
    entry = {"score": game.score, "multiple": round(float(game.multiple), 4),
             "date": (when or date.today()).isoformat(), "seed": game.seed, "timed": game.config.timed}
    rank = next((i for i, e in enumerate(entries) if game.score > e["score"]), len(entries))
    entries.insert(rank, entry)
    data[k] = entries[:TOP]
    storage.write_json(SCORES_FILE, data)
    return rank + 1 if rank < TOP else None


# ── review ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Summary:
    grades: dict[str, int]
    lightning: int
    fast: int
    best_combo: Fraction
    best_streak: int
    benchmark: Fraction
    worst: Any  # Bet | None
    worst_lost: int


def ideal_points(bet: Any) -> int:
    """What the best possible play would have scored at this bet's speed and combo: a PERFECT, or a
    DISCIPLINE sit-out when the bet had no edge (no PERFECT exists there)."""
    return points(PERFECT if bet.odds.k > 0 else DISCIPLINE, bet.tier, bet.streak_before)


def summary(game: HiloGame) -> Summary:
    grades = Counter(b.grade for b in game.bets)
    scored = [b for b in game.bets if b.grade in STREAK_GRADES]
    worst = max(game.bets, key=lambda b: (ideal_points(b) - b.points, -b.number), default=None)
    return Summary(
        grades={g: grades.get(g, 0) for g in GRADES},
        lightning=sum(1 for b in scored if b.tier == LIGHTNING),
        fast=sum(1 for b in scored if b.tier == FAST),
        best_combo=game.best_combo,
        best_streak=game.best_streak,
        benchmark=benchmark(game.config.deck, game.cards, game.start),
        worst=worst,
        worst_lost=ideal_points(worst) - worst.points if worst else 0,
    )


def multipliers(bet: Any) -> str:
    """"LIGHTNING ×2 · combo ×1.3" (speed only shows when it counted)."""
    parts = []
    if bet.grade in STREAK_GRADES and bet.tier in (LIGHTNING, FAST):
        parts.append(f"{bet.tier} ×{float(SPEED[bet.tier]):g}")
    if combo_multiplier(bet.streak_before) > 1:
        parts.append(f"combo ×{float(combo_multiplier(bet.streak_before)):g}")
    return " · ".join(parts)


def review_rows(game: HiloGame) -> list[tuple[str, ...]]:
    """#, showing, h/same/l, right side + size, your side + size, grade, multipliers, points, capital after."""
    rows = []
    for b in game.bets:
        o = b.odds
        right = f"{o.right} {pct(o.k)}%" if o.right else "none · 0%"
        yours = "timeout" if b.timeout else ("sit out" if b.percent == 0 else f"{b.side} {b.percent}%")
        rows.append((
            str(b.number), "—" if b.showing is None else str(b.showing), f"{o.h}/{o.same}/{o.l}", right, yours,
            b.grade, multipliers(b), f"{b.points:+d}", f"{b.capital_after:,}",
        ))
    return rows


def history_record(game: HiloGame, when: datetime | None = None) -> dict[str, Any]:
    return {
        "game": "hilo",
        "ts": (when or datetime.now()).isoformat(timespec="seconds"),
        "mode": game.mode,
        "deck": game.config.deck,
        "seed": game.seed,
        "config": game.config.to_dict(),
        "bets": len(game.bets),
        "score": game.score,
        "final_balance": game.capital,
        "multiple": round(float(game.multiple), 4),
        "bust": game.bust,
    }
