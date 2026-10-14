"""The Mental Math daily challenge: the Detroit date, one attempt per day (~/.met_games/daily.json), the streak,
and the pasteable score card. Problems come from the frozen generator in daily_v1.py. Pure Python."""

from __future__ import annotations

import shutil
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
from math import floor
from typing import Any
from zoneinfo import ZoneInfo

from met_games import storage
from met_games.games.math import daily_v1
from met_games.games.math.config import DAILY, FLOW, OPTIVER, ZETAMAC
from met_games.games.math.problems import FAMILIES, FAMILY_LABELS, MEDIUM, Problem
from met_games.games.math.run import ListStream, Run

DETROIT = ZoneInfo("America/Detroit")
# Daily #1. The release date; never change it, or every daily number shifts.
DAILY_EPOCH = date(2026, 10, 11)
DAILY_FILE = "daily.json"
DAILY_MS = 120_000
VERSION = daily_v1.VERSION
SQUARES = 5


def today(now: datetime | None = None) -> date:
    """The daily's date: today in America/Detroit, whatever the machine's timezone."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(DETROIT).date()


def number(day: date) -> int:
    return (day - DAILY_EPOCH).days + 1


def seconds_to_next(now: datetime | None = None) -> int:
    """Seconds until Detroit midnight, when the next daily opens."""
    now = (now or datetime.now(timezone.utc)).astimezone(DETROIT)
    midnight = datetime.combine(now.date() + timedelta(days=1), time(0), DETROIT)
    return int((midnight.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds())


def problems(day: date) -> list[Problem]:
    return [Problem(*p) for p in daily_v1.problems(day)]


def new_daily_run(day: date) -> Run:
    """Sprint 2:00, MEDIUM, all four families, on the day's 200 frozen problems."""
    run = Run(DAILY, ListStream(problems(day)), duration_ms=DAILY_MS, board=MEDIUM, seed=daily_v1.seed_for(day))
    run.day = day
    return run


# ── one attempt per day ─────────────────────────────────────────────────────


def load_state() -> dict[str, Any]:
    data = storage.read_json(DAILY_FILE, {})
    if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
        return {"days": {}}
    return data


def started(day: date) -> bool:
    return day.isoformat() in load_state()["days"]


def start(day: date, when: datetime | None = None) -> bool:
    """Write the date before the run starts (honor system: one attempt). False if today was already started."""
    state = load_state()
    if day.isoformat() in state["days"]:
        return False
    state["days"][day.isoformat()] = {"started": (when or datetime.now()).isoformat(timespec="seconds"),
                                      "result": None}
    storage.write_json(DAILY_FILE, state)
    return True


def family_accuracy(attempts: list[Any]) -> dict[str, list[int]]:
    """{family: [right, seen]} for every family."""
    out = {f: [0, 0] for f in FAMILIES}
    for a in attempts:
        out[a.problem.family][1] += 1
        out[a.problem.family][0] += a.correct
    return out


def result_of(run: Run) -> dict[str, Any]:
    out = {"correct": run.correct, "skipped": run.skipped, "points": run.points,
           "best_combo": str(run.best_combo), "families": family_accuracy(run.attempts)}
    if run.ended_early:
        out["ended_early"] = True
    return out


def save_result(day: date, run: Run) -> None:
    state = load_state()
    entry = state["days"].setdefault(day.isoformat(), {"started": None})
    entry["result"] = result_of(run)
    storage.write_json(DAILY_FILE, state)


def result(day: date) -> dict[str, Any] | None:
    entry = load_state()["days"].get(day.isoformat())
    return entry.get("result") if entry else None


def streak(day: date) -> int:
    """Consecutive days played, ending today (or yesterday, if today isn't played yet)."""
    days = set(load_state()["days"])
    d = day if day.isoformat() in days else day - timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n


# ── the score card ──────────────────────────────────────────────────────────


def squares(right: int, seen: int) -> str:
    """Accuracy in fifths, rounded half up: ■■■■□ = 80%."""
    filled = floor(Fraction(right, seen) * SQUARES + Fraction(1, 2)) if seen else 0
    return "■" * filled + "□" * (SQUARES - filled)


def family_lines(families: dict[str, list[int]]) -> list[str]:
    cells = [f"{FAMILY_LABELS[f]:<4} {squares(*families.get(f, (0, 0)))}" for f in FAMILIES]
    return [f"{cells[0]}   {cells[1]}", f"{cells[2]}   {cells[3]}"]


def score_line(correct: int, points: int, best_combo: Fraction) -> str:
    return f"{correct} ✓ · {points:,} pts · best ×{float(best_combo):.1f}"


def daily_card(day: date, res: dict[str, Any]) -> str:
    return "\n".join([
        f"MET MATH · daily #{number(day)} · sprint M · {VERSION}",
        score_line(res["correct"], res["points"], Fraction(res["best_combo"])),
        *family_lines(res["families"]),
        "met-games math --daily",
    ])


def run_card(run: Any) -> str:
    """The same card for any other run, with the command that replays its seed."""
    if run.mode == DAILY:
        return daily_card(run.day, result_of(run))
    if run.mode == ZETAMAC:
        head, score = "zetamac 120s", f"{run.correct} ✓ · raw score"
    elif run.mode == OPTIVER:
        head, score = "optiver-style 80/8", f"{run.correct} ✓ · {run.wrong} ✗ · net {run.correct - run.wrong:+d}"
    elif run.mode == FLOW:
        head, score = "flow-style 60/6", f"{run.correct} ✓ · {run.wrong} ✗ of 60 · unofficial practice format"
    else:
        head, score = f"{run.mode} {run.board[0].upper()}", score_line(run.correct, run.points, run.best_combo)
    cmd = f"met-games math --mode {run.mode}"
    if run.mode not in (ZETAMAC, OPTIVER, FLOW) and run.board in ("easy", "medium", "hard"):
        cmd += f" --difficulty {run.board}"
    return "\n".join([f"MET MATH · {head} · seed {run.seed}", score, *family_lines(family_accuracy(run.attempts)),
                      f"{cmd} --seed {run.seed}"])


def copy(text: str) -> bool:
    """Copy to the clipboard with pbcopy; False if pbcopy isn't there (the caller shows the card instead)."""
    if shutil.which("pbcopy") is None:
        return False
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True

