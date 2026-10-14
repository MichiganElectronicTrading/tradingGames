"""Mental Math history (~/.met_games/math_history.jsonl, one line per problem shown), run summaries
(math_runs.jsonl), bests (math_bests.json), and the post-run weakness report. Pure Python."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Any

from met_games import storage
from met_games.games.math import adaptive
from met_games.games.math.config import CHAIN, DAILY, DRILL, ESTIMATE, FLOW, OPTIVER, PROB_DRILL, ZETAMAC
from met_games.games.math.ladder import anchor_of
from met_games.games.math.problems import FAMILIES, LEVELS, MEDIUM, SUBTYPE_LABELS, SUBTYPES
from met_games.games.math.run import CORRECT, Attempt
from met_games.games.math.tips import render

HISTORY_FILE = "math_history.jsonl"
RUNS_FILE = "math_runs.jsonl"
BESTS_FILE = "math_bests.json"
USUAL_WINDOW = 200  # "your usual" = median over a subtype's last 200 logged answers
USUAL_MIN = 10  # fewer samples than this: "—"
SAME_WITHIN = Fraction(3, 10)  # |run avg − usual| under 0.3 s reads "same"
SUBTYPE_ORDER = [s for f in FAMILIES for s in dict.fromkeys(x for lv in SUBTYPES[f].values() for x in lv)]


# ── logging ─────────────────────────────────────────────────────────────────


def json_number(x: Fraction | int) -> int | float:
    """A score for JSON: whole numbers as ints; Estimate's half points (x.5) as floats, which hold them exactly."""
    x = Fraction(x)
    return x.numerator if x.denominator == 1 else float(x)


def problem_records(run: Any, when: datetime) -> list[dict[str, Any]]:
    stamp = when.isoformat(timespec="seconds")
    if hasattr(run, "log_rows"):  # Chain and Estimate write their own lines
        head = {"date": when.date().isoformat(), "run": stamp, "mode": run.mode, "difficulty": run.board}
        return [{**head, **row} for row in run.log_rows()]
    return [{
        "date": when.date().isoformat(), "run": stamp, "mode": run.mode, "difficulty": run.board,
        "level": a.problem.level, "family": a.problem.family, "subtype": a.problem.subtype, "outcome": a.outcome,
        "ms": a.ms,
    } for a in run.attempts]


def run_record(run: Any, when: datetime) -> dict[str, Any]:
    record = {
        "date": when.date().isoformat(), "ts": when.isoformat(timespec="seconds"), "mode": run.mode,
        "difficulty": run.board, "seed": run.seed, "correct": run.correct, "skipped": run.skipped,
        "wrong": run.wrong, "points": json_number(run.points), "best_combo": str(run.best_combo),
    }
    if getattr(run, "focus", None):
        record["focus"] = run.focus
    if hasattr(run, "summary"):
        record.update(run.summary())
    return record


def log_run(run: Any, when: datetime | None = None) -> None:
    """Every problem shown (and answered or skipped) to the history, plus one run summary."""
    when = when or datetime.now()
    for rec in problem_records(run, when):
        storage.append_jsonl(HISTORY_FILE, rec)
    storage.append_jsonl(RUNS_FILE, run_record(run, when))


def load_history() -> list[dict[str, Any]]:
    return storage.read_history(HISTORY_FILE)


def load_runs() -> list[dict[str, Any]]:
    return storage.read_jsonl(RUNS_FILE)


# ── "your usual" ────────────────────────────────────────────────────────────


def median(values: list[int]) -> Fraction:
    xs = sorted(values)
    mid = len(xs) // 2
    return Fraction(xs[mid]) if len(xs) % 2 else Fraction(xs[mid - 1] + xs[mid], 2)


def usual_ms(history: list[dict[str, Any]], subtype: str) -> Fraction | None:
    """Median answer time (ms) over this subtype's last 200 logged correct answers; None under 10 samples."""
    times = [r["ms"] for r in history if r.get("subtype") == subtype and r.get("outcome") == CORRECT][-USUAL_WINDOW:]
    return median(times) if len(times) >= USUAL_MIN else None


def vs_usual(avg_ms: Fraction | None, usual: Fraction | None) -> tuple[str, Fraction | None]:
    """("faster by 0.8s" | "slower by 1.2s" | "same" | "—", the difference in seconds)."""
    if avg_ms is None or usual is None:
        return "—", None
    diff = (avg_ms - usual) / 1000
    if abs(diff) < SAME_WITHIN:
        return "same", diff
    return f"{'faster' if diff < 0 else 'slower'} by {abs(float(diff)):.1f}s", diff


# ── the report ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SubtypeRow:
    family: str
    subtype: str
    seen: int
    right: int
    avg_ms: Fraction | None  # over correct answers
    usual_ms: Fraction | None
    vs: str
    diff: Fraction | None  # seconds vs usual (+ = slower)

    @property
    def accuracy(self) -> Fraction:
        return Fraction(self.right, self.seen)

    @property
    def label(self) -> str:
        return SUBTYPE_LABELS[self.subtype]


def mean_ms(attempts: list[Attempt]) -> Fraction | None:
    times = [a.ms for a in attempts if a.correct]
    return Fraction(sum(times), len(times)) if times else None


def subtype_rows(attempts: list[Attempt], history: list[dict[str, Any]]) -> list[SubtypeRow]:
    """One row per subtype seen this run, in family order; `history` is everything logged before this run."""
    rows = []
    for sub in SUBTYPE_ORDER:
        mine = [a for a in attempts if a.problem.subtype == sub]
        if not mine:
            continue
        avg = mean_ms(mine)
        usual = usual_ms(history, sub)
        vs, diff = vs_usual(avg, usual)
        rows.append(SubtypeRow(mine[0].problem.family, sub, len(mine), sum(a.correct for a in mine), avg, usual, vs,
                               diff))
    return rows


def weakest(rows: list[SubtypeRow], n: int = 2) -> list[SubtypeRow]:
    """Lowest accuracy first; ties go to the slowest against your usual, then the slowest average."""
    return sorted(rows, key=lambda r: (r.accuracy, -(r.diff or 0), -(r.avg_ms or 0)))[:n]


def slowest(attempts: list[Attempt], n: int = 3) -> list[Attempt]:
    return sorted(attempts, key=lambda a: -a.ms)[:n]


def drill_pool(rows: list[SubtypeRow], attempts: list[Attempt] | None = None) -> list[tuple[str, ...]]:
    """The drill's problem pool: the run's two weakest subtypes — with `attempts`, each at the difficulty it was
    seen at (an adaptive level at its nearest anchor; Zetamac's arithmetic drills at MEDIUM)."""
    pool = []
    for r in weakest(rows):
        if attempts is None:
            pool.append((r.family, r.subtype))
            continue
        level = anchor_of(next(a.problem.level for a in attempts if a.problem.subtype == r.subtype))
        pool.append((r.family, r.subtype, level if level in LEVELS else MEDIUM))
    return pool


@dataclass(frozen=True)
class Report:
    rows: list[SubtypeRow]
    weak: list[SubtypeRow]
    slowest: list[Attempt]
    avg_ms: Fraction | None
    shortcut: tuple[str, str, str | None] | None  # (title, rule, example) for the slowest problem
    last_runs: list[dict[str, Any]]


def last_runs(runs: list[dict[str, Any]], mode: str, difficulty: str, n: int = 5) -> list[dict[str, Any]]:
    return [r for r in runs if r.get("mode") == mode and r.get("difficulty") == difficulty][-n:]


def build_report(run: Any, history: list[dict[str, Any]], runs: list[dict[str, Any]]) -> Report:
    """`history` and `runs` as logged before this run; `runs` should already include this run's summary."""
    rows = subtype_rows(run.attempts, history)
    slow = slowest(run.attempts)
    shortcut = render(slow[0].problem.tip_key, slow[0].problem) if slow else None
    return Report(rows, weakest(rows), slow, mean_ms(run.attempts), shortcut, last_runs(runs, run.mode, run.board))


# ── bests ───────────────────────────────────────────────────────────────────


def best_fields(mode: str) -> tuple[str, ...]:
    return {ZETAMAC: ("raw",), OPTIVER: ("net",), CHAIN: ("length", "points"), ESTIMATE: ("points",),
            FLOW: ("correct",), PROB_DRILL: ("correct",)}.get(mode, ("correct", "points"))


def run_values(run: Any) -> dict[str, int | float]:
    return {"correct": run.correct, "points": json_number(run.points), "raw": run.correct,
            "net": run.correct - run.wrong, "length": getattr(run, "length", 0)}


def best_key(mode: str, difficulty: str) -> str:
    return f"{mode}/{difficulty}"


def load_bests() -> dict[str, dict[str, Any]]:
    data = storage.read_json(BESTS_FILE, {})
    return data if isinstance(data, dict) else {}


def record_bests(run: Any, when: datetime | None = None) -> list[str]:
    """File this run's bests for its mode × difficulty; returns the fields it beat (or set, if above 0). Drills
    and the daily never count."""
    if run.mode in (DRILL, DAILY):
        return []
    data = load_bests()
    key = best_key(run.mode, run.board)
    entry = data.get(key, {})
    values = run_values(run)
    beaten = [f for f in best_fields(run.mode) if values[f] > entry.get(f, 0)]
    if beaten:
        day = (when or datetime.now()).date().isoformat()
        for f in beaten:
            entry[f] = values[f]
            entry[f"{f}_date"] = day
        data[key] = entry
        storage.write_json(BESTS_FILE, data)
    return beaten



def file_run(run: Any, when: datetime | None = None) -> tuple[Report, list[str]]:
    """At the end of a run: log it, build its report against the history from before it, file its bests, and
    (adaptive) save where its levels ended up."""
    before = load_history()
    log_run(run, when)
    if getattr(run, "ladder", None) is not None:
        adaptive.save_levels(run.ladder.levels, (when or datetime.now()).date())
    return build_report(run, before, load_runs()), record_bests(run, when)


def file_arcade(run: Any, when: datetime | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """At the end of a Chain, Estimate or Probability drill run: log it, file its bests and (adaptive) save its
    levels. Returns (bests beaten, the last 5 runs on this mode × difficulty, this one included)."""
    log_run(run, when)
    if getattr(run, "ladder", None) is not None:
        adaptive.save_levels(run.ladder.levels, (when or datetime.now()).date())
    beaten = record_bests(run, when)
    return beaten, last_runs(load_runs(), run.mode, run.board)


def lifetime(history: list[dict[str, Any]]) -> list[tuple[str, int, int, Fraction | None]]:
    """MY STATS: per subtype ever logged — (subtype, seen, right, median ms of correct answers)."""
    out = []
    for sub in SUBTYPE_ORDER:
        mine = [r for r in history if r.get("subtype") == sub]
        if mine:
            times = [r["ms"] for r in mine if r.get("outcome") == CORRECT]
            out.append((sub, len(mine), len(times), median(times) if times else None))
    return out
