"""MY STATS: progress over time from the history, the run summaries, the bests and the adaptive levels.
Pure Python, exact arithmetic, no Textual."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any

from met_games.games.math.config import (
    ADAPTIVE,
    CHAIN,
    CUSTOM,
    ESTIMATE,
    FLOW,
    OPTIVER,
    PROB_DRILL,
    SPRINT,
    STANDARD,
    SURVIVAL,
    ZETAMAC,
)
from met_games.games.math.adaptive import arrow
from met_games.games.math.history import best_fields, best_key, median
from met_games.games.math.ladder import SUBTYPE_TRACK, TRACKS
from met_games.games.math.problems import EASY, FAMILIES, HARD, MEDIUM

BARS = "▁▂▃▄▅▆▇█"
SPARK_RUNS = 20
SPLIT_RUNS = 10  # first 10 vs last 10 runs
SPLIT_MIN = 2 * SPLIT_RUNS
ACCURACY_WINDOW = 100
PRIMARY = {SPRINT: "correct", SURVIVAL: "correct", ZETAMAC: "correct", OPTIVER: "net", CHAIN: "length",
           ESTIMATE: "points", FLOW: "correct", PROB_DRILL: "correct"}
# MY STATS' mode tabs (←→ wraps)
STATS_MODES = (SPRINT, SURVIVAL, CHAIN, ESTIMATE, ZETAMAC, FLOW, PROB_DRILL, OPTIVER)
PRIMARY_LABELS = {"correct": "correct", "net": "net", "length": "chain length", "points": "points"}
STATS_DIFFICULTIES = {SPRINT: (EASY, MEDIUM, HARD, CUSTOM, ADAPTIVE), SURVIVAL: (EASY, MEDIUM, HARD, CUSTOM, ADAPTIVE),
                      CHAIN: (EASY, MEDIUM, HARD, CUSTOM), ESTIMATE: (EASY, MEDIUM, HARD), ZETAMAC: (STANDARD,),
                      OPTIVER: (STANDARD,), FLOW: (STANDARD,), PROB_DRILL: (EASY, MEDIUM, HARD, ADAPTIVE)}
# "Its best difficulty": the hardest one with a best on file
HARDEST_FIRST = (HARD, MEDIUM, EASY, ADAPTIVE, CUSTOM, STANDARD)


def exact(x: Any) -> Fraction:
    """A stored number (Estimate's half points are floats on disk) as an exact Fraction."""
    return Fraction(str(x))


# ── sparkline ───────────────────────────────────────────────────────────────


def sparkline(values: list[Any]) -> str:
    """▁–█ scaled to these values' own min and max; all equal → a flat middle line."""
    xs = [exact(v) for v in values]
    if not xs:
        return ""
    lo, hi = min(xs), max(xs)
    if lo == hi:
        return BARS[len(BARS) // 2 - 1] * len(xs)
    top = len(BARS) - 1
    return "".join(BARS[int((x - lo) * top / (hi - lo) + Fraction(1, 2))] for x in xs)


def primary(record: dict[str, Any]) -> Fraction:
    mode = record.get("mode")
    if mode == OPTIVER:
        return exact(record.get("correct", 0)) - exact(record.get("wrong", 0))
    return exact(record.get(PRIMARY.get(mode, "correct"), 0))


def recent(runs: list[dict[str, Any]], mode: str, difficulty: str, n: int = SPARK_RUNS) -> list[Fraction]:
    """The primary stat of the last `n` runs on this mode × difficulty, oldest first (focus drills aside)."""
    return [primary(r) for r in runs if r.get("mode") == mode and r.get("difficulty") == difficulty][-n:]


def trend(values: list[Fraction]) -> tuple[Fraction, Fraction, Fraction] | None:
    """(first, median, latest)."""
    if not values:
        return None
    xs = sorted(values)
    mid = len(xs) // 2
    med = xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2
    return values[0], med, values[-1]


def number(x: Fraction) -> str:
    """1,234 or 37.5 (one place, from the exact value)."""
    if x.denominator == 1:
        return f"{x.numerator:,}"
    return f"{(Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal('0.1')):,}"


# ── median time per family, first 10 vs last 10 runs ────────────────────────


def run_order(history: list[dict[str, Any]]) -> list[str]:
    """Every run in the history, in order (all modes)."""
    return list(dict.fromkeys(r["run"] for r in history if r.get("run")))


def family_split(history: list[dict[str, Any]]) -> dict[str, tuple[Fraction | None, Fraction | None]] | None:
    """Per family: (median ms of correct answers over the first 10 runs, the same over the last 10). None with fewer
    than 20 runs."""
    runs = run_order(history)
    if len(runs) < SPLIT_MIN:
        return None
    first, last = set(runs[:SPLIT_RUNS]), set(runs[-SPLIT_RUNS:])

    def med(family: str, window: set[str]) -> Fraction | None:
        times = [r["ms"] for r in history if r.get("run") in window and r.get("family") == family
                 and r.get("outcome") == "correct"]
        return median(times) if times else None

    return {f: (med(f, first), med(f, last)) for f in FAMILIES}


# ── tracks ──────────────────────────────────────────────────────────────────


def track_of(record: dict[str, Any]) -> str | None:
    """A history line's skill track (Chain lines carry it; Estimate's have none)."""
    return record.get("track") or SUBTYPE_TRACK.get(record.get("subtype", ""))


def level_rows(levels: dict[str, int] | None, week: dict[str, int] | None,
               tracks: tuple[str, ...] = TRACKS) -> list[tuple[str, int | None, str]]:
    """(track, level, ▲/▼/· against the snapshot from 7 days ago) for every track."""
    return [(t, levels.get(t) if levels else None,
             arrow(levels[t], (week or {}).get(t)) if levels and t in levels else "·") for t in tracks]


def accuracy_by_track(history: list[dict[str, Any]], window: int = ACCURACY_WINDOW) -> dict[str, Fraction]:
    """Accuracy per track over the last `window` problems that have a track."""
    tracked = [r for r in history if track_of(r)][-window:]
    out = {}
    for t in TRACKS:
        mine = [r for r in tracked if track_of(r) == t]
        if mine:
            out[t] = Fraction(sum(r.get("outcome") == "correct" for r in mine), len(mine))
    return out


def focus_next(levels: dict[str, int] | None, week: dict[str, int] | None,
               history: list[dict[str, Any]]) -> tuple[str, str] | None:
    """(track, why): the biggest 7-day level drop; if nothing dropped, the lowest accuracy over the last 100
    problems. None without any data."""
    if levels and week:
        drops = {t: week[t] - levels[t] for t in TRACKS if t in levels and t in week}
        worst = max(drops.values(), default=0)
        if worst > 0:
            t = next(t for t in TRACKS if drops.get(t) == worst)
            return t, f"down {worst} level{'s' if worst > 1 else ''} in 7 days"
    acc = accuracy_by_track(history)
    if not acc:
        return None
    low = min(acc.values())
    t = next(t for t in TRACKS if acc.get(t) == low)
    return t, f"{int(low * 100 + Fraction(1, 2))}% right over your last {ACCURACY_WINDOW} problems"


# ── bests and the header ────────────────────────────────────────────────────


def best_rows(bests: dict[str, dict[str, Any]]) -> list[tuple[str, str | None, dict[str, Any]]]:
    """Every mode at its best difficulty (the hardest with a best on file): (mode, difficulty or None, entry)."""
    rows = []
    for mode in STATS_MODES:
        found = next(((d, bests[best_key(mode, d)]) for d in HARDEST_FIRST if best_key(mode, d) in bests), None)
        rows.append((mode, found[0], found[1]) if found else (mode, None, {}))
    return rows


def best_value(mode: str, entry: dict[str, Any]) -> tuple[str, Any, str | None] | None:
    """(field, value, date) of the mode's first best field, or None."""
    for f in best_fields(mode):
        if f in entry:
            return f, entry[f], entry.get(f"{f}_date")
    return None


def header(runs: list[dict[str, Any]]) -> tuple[int, str | None]:
    """(total runs, the first run's date)."""
    dates = [r["date"] for r in runs if r.get("date")]
    return len(runs), (min(dates) if dates else None)
