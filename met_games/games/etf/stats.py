"""ETF Arb recap math, mistakes, history records and CSV rows. Pure Python, Decimal money."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from met_games.games.etf.engine import NAMES, TICK, TIMEOUT, YOU, Decision, EtfGame, Fill, Round
from met_games.games.etf.model import BUY, SELL, SKIP, fmt_px, right_call

D = Decimal


def money(x: Decimal) -> str:
    """Signed dollars to the cent: +$37.20 / -$5.00."""
    c = x.quantize(D("0.01"), rounding=ROUND_HALF_UP)
    return f"{'-' if c < 0 else '+'}${abs(c):,.2f}"


def right_way(fill: Fill) -> bool:
    """Traded the side whose edge is positive at NAV (gross > 0)."""
    return fill.gross > 0


def you(r: Round) -> Decision:
    return r.decisions[YOU]


def left_before(r: Round, fill: Fill) -> int:
    """Units left on the fill's side just before it traded."""
    taken = sum(f.units for f in r.fills[: r.fills.index(fill)] if f.side == fill.side)
    return r.size - taken


def missed_at_max(game: EtfGame, r: Round) -> Decimal:
    """What the right call would have made at max size (before any bonus)."""
    call, edge = game.right_call(r)
    return edge * game.right_units(r) - game.config.fee if call != SKIP else D(0)


def naive_call(game: EtfGame, r: Round) -> str:
    """The right call if you ignore the round's event (the trap)."""
    p = r.plan
    return right_call(p.naive_nav, p.bid, p.ask, game.right_units(r), game.config.fee)[0]


def action_of(d: Decision) -> str:
    return SKIP if d.action == TIMEOUT else d.action


def mistakes(game: EtfGame) -> list[str]:
    out: list[str] = []
    cfg = game.config
    for r in game.rounds:
        if r.end is None:
            continue
        d = you(r)
        call, edge = game.right_call(r)
        n = r.number
        if d.fill:
            f = d.fill
            if not right_way(f):
                out.append(f"R{n}: wrong direction — {f.side} {f.units} @ {fmt_px(f.price, r.plan.tick)} with NAV "
                           f"{fmt_px(r.nav, r.plan.tick)} "
                           f"({money(f.net)})")
            elif f.net < 0:
                most = min(cfg.max_units, left_before(r, f))
                better = (f.gross / f.units) * most - f.fee
                if better > 0:
                    out.append(f"R{n}: right side but too small — {f.units} units netted {money(f.net)}; "
                               f"{most} would have made {money(better)}")
            if call == SKIP:
                out.append(f"R{n}: traded on a skip round — the gap ({fmt_px(edge, r.plan.tick)}) couldn't cover the "
                           f"${cfg.fee:g} fee")
        elif call != SKIP:
            what = "timed out" if d.action == TIMEOUT else "skipped"
            out.append(f"R{n}: {what} a trade round — {call} {game.right_units(r)} would have made "
                       f"{money(missed_at_max(game, r))}")
        if r.plan.event and action_of(d) == naive_call(game, r) != call:
            out.append(f"R{n}: fell for the event — {r.plan.event.ticker} {r.plan.event.chg_label}: you acted on "
                       "the table's weight instead of the adjusted one")
    return out


@dataclass(frozen=True)
class Tiles:
    right_trades: int
    trades: int
    right_skips: int
    skip_rounds: int
    first: int
    avg_decision: float | None


def tiles(game: EtfGame) -> Tiles:
    done = [r for r in game.rounds if r.end is not None]
    fills = [you(r).fill for r in done if you(r).fill]
    skip_rounds = [r for r in done if game.right_call(r)[0] == SKIP]
    times = [you(r).t * TICK for r in done if you(r).action != TIMEOUT and you(r).t is not None]
    return Tiles(
        right_trades=sum(1 for f in fills if right_way(f)),
        trades=len(fills),
        right_skips=sum(1 for r in skip_rounds if not you(r).fill),
        skip_rounds=len(skip_rounds),
        first=sum(1 for r in done if r.first and r.first.who == YOU),
        avg_decision=sum(times) / len(times) if times else None,
    )


def leaderboard(game: EtfGame) -> list[tuple[int, str, Decimal]]:
    totals = [game.total(s) for s in range(len(NAMES))]
    order = sorted(range(len(NAMES)), key=lambda s: (-totals[s], s))
    return [(1 + sum(1 for q in range(len(NAMES)) if totals[q] > totals[s]), NAMES[s], totals[s]) for s in order]


def size_story(game: EtfGame, r: Round, side: str) -> str:
    """How a side's size was used: "ask 40 → 20 (MERLIN 20) → 0 (YOU 20)" or "bid 40 untouched"."""
    label = "ask" if side == BUY else "bid"
    fills = [f for f in r.fills if f.side == side]
    if not fills:
        return f"{label} {r.size} untouched"
    left, parts = r.size, [f"{label} {r.size}"]
    for f in fills:
        left -= f.units
        parts.append(f"{left} ({NAMES[f.who]} {f.units})")
    return " → ".join(parts)


def history_record(game: EtfGame, when: datetime | None = None) -> dict[str, Any]:
    """One JSON line per session; keys the shared Stats screen reads (no P&L report in this game)."""
    fills = [you(r).fill for r in game.rounds if r.end is not None and you(r).fill]
    return {
        "game": game.source.key,
        "ts": (when or datetime.now()).isoformat(timespec="seconds"),
        "mode": game.mode,
        "seed": game.seed,
        "config": game.config.to_dict(),
        "rounds_played": sum(1 for r in game.rounds if r.end is not None),
        "net": float(game.total(YOU)),
        "final_balance": float(game.total(YOU)),
        "edge_taken": float(sum((f.gross for f in fills), D(0))),
        "reports_correct": 0,
        "reports_total": 0,
        "ended_early": False,
        "end_reason": None,
    }


def csv_rows(game: EtfGame) -> list[list[Any]]:
    rows: list[list[Any]] = [[
        "round", "event", "nav", "bid", "ask", "right_call", "right_gap", "who", "action", "units", "price", "t_s",
        "gross", "fee", "bonus", "net", "first",
    ]]
    for r in game.rounds:
        if r.end is None:
            continue
        call, edge = game.right_call(r)
        event = r.plan.event
        for who in range(len(NAMES)):
            d = r.decisions[who]
            f = d.fill
            rows.append([
                r.number, f"{event.ticker} {event.kind}" if event else "", r.nav, r.plan.bid, r.plan.ask, call, edge,
                NAMES[who], d.action, f.units if f else 0, f.price if f else "",
                "" if d.t is None else d.t * TICK, f.gross if f else 0, f.fee if f else 0, f.bonus if f else 0,
                d.net, bool(f and f.first),
            ])
    return rows
