"""Session recap math, history records and CSV rows for any sum game. Pure Python."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from mtt_games.games.sumgame.engine import MISSED_EDGE, PASS, TIMEOUT, Money, Round, SumSession


def money(x: Any, decimals: int = 0) -> str:
    sign = "-" if x < 0 else "+"
    return f"{sign}${abs(x):,.{decimals}f}"


def trade_label(rnd: Round) -> str:
    d = rnd.decision
    if d is None:
        return "—"
    if d.action == PASS:
        return "PASS"
    if d.action == TIMEOUT:
        return "TIMEOUT"
    return f"{d.action.upper()} {d.size} @ {rnd.SOURCE.price(d.price)}"


@dataclass(frozen=True)
class SessionStats:
    start_balance: Money
    final_balance: Money
    edge_taken: float
    realized: Money
    luck: float
    reports_correct: int
    reports_total: int
    avg_answer_s: float | None
    rounds_played: int

    @property
    def change(self) -> Money:
        return self.final_balance - self.start_balance


def played(session: SumSession) -> list[Round]:
    return [r for r in session.rounds if r.decision is not None]


def session_stats(session: SumSession) -> SessionStats:
    rounds = played(session)
    edge = sum(r.decision.edge_dollars for r in rounds)
    realized = sum((r.pnl for r in rounds), session.source.to_money(0))
    reported = [r for r in rounds if r.reported is not None]
    times = [r.answer_time for r in reported if r.answer_time is not None]
    return SessionStats(
        start_balance=session.source.to_money(session.config.budget),
        final_balance=session.balance,
        edge_taken=edge,
        realized=realized,
        luck=float(realized) - edge,
        reports_correct=sum(1 for r in reported if r.report_correct),
        reports_total=len(reported),
        avg_answer_s=sum(times) / len(times) if times else None,
        rounds_played=len(rounds),
    )


def mistakes(session: SumSession) -> list[str]:
    price = session.source.price
    out: list[str] = []
    for r in played(session):
        d = r.decision
        if d.is_trade and d.edge_per_unit < 0:
            out.append(
                f"R{r.number}: {trade_label(r)} vs fair {d.fair:.2f} — edge {d.edge_per_unit:+.2f}/unit "
                f"({money(d.edge_dollars, 2)})"
            )
        if d.action == PASS and d.best_edge >= MISSED_EDGE:
            out.append(
                f"R{r.number}: passed on {d.best_edge:.2f}/unit of edge "
                f"({price(d.bid)} @ {price(d.ask)}, fair {d.fair:.2f})"
            )
        if d.action == TIMEOUT:
            out.append(f"R{r.number}: timed out")
        if r.reported is not None and not r.report_correct:
            out.append(f"R{r.number}: reported P&L {price(r.reported)}, actual {price(r.pnl)}")
    return out


def bankroll(session: SumSession) -> list[Money]:
    return [session.source.to_money(session.config.budget)] + [r.balance_after for r in played(session)]


def _num(x: Any) -> Any:
    """JSON-friendly number: ints stay ints, Decimals become floats."""
    return float(x) if isinstance(x, Decimal) else x


def history_record(session: SumSession, when: datetime | None = None) -> dict[str, Any]:
    s = session_stats(session)
    return {
        "game": session.source.key,
        "ts": (when or datetime.now()).isoformat(timespec="seconds"),
        "mode": session.mode,
        "seed": session.seed,
        "config": session.config.to_dict(),
        "rounds_played": s.rounds_played,
        "start_balance": _num(s.start_balance),
        "final_balance": _num(s.final_balance),
        "edge_taken": round(s.edge_taken, 4),
        "realized": _num(s.realized),
        "luck": round(s.luck, 4),
        "reports_correct": s.reports_correct,
        "reports_total": s.reports_total,
        "avg_answer_s": None if s.avg_answer_s is None else round(s.avg_answer_s, 2),
        "ended_early": session.end_reason is not None,
        "end_reason": session.end_reason,
    }


@dataclass(frozen=True)
class ModeStats:
    mode: str
    sessions: int
    best_final: float
    avg_edge_taken: float
    report_accuracy: float | None  # 0–1, None if nothing reported


def mode_stats(records: Iterable[dict[str, Any]]) -> list[ModeStats]:
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_mode.setdefault(rec.get("mode", "CUSTOM"), []).append(rec)
    order = ["EASY", "MEDIUM", "HARD", "CUSTOM"]
    out = []
    for mode in sorted(by_mode, key=lambda m: (order.index(m) if m in order else len(order), m)):
        recs = by_mode[mode]
        total = sum(r.get("reports_total", 0) for r in recs)
        correct = sum(r.get("reports_correct", 0) for r in recs)
        out.append(
            ModeStats(
                mode=mode,
                sessions=len(recs),
                best_final=max(r.get("final_balance", 0) for r in recs),
                avg_edge_taken=sum(r.get("edge_taken", 0.0) for r in recs) / len(recs),
                report_accuracy=correct / total if total else None,
            )
        )
    return out


def csv_rows(session: SumSession) -> list[list[Any]]:
    src = session.source
    rows: list[list[Any]] = [[
        "round", "event", src.noun, "bid", "ask", "fair", "trade", "size", "edge_per_unit", "edge_dollars",
        "settle", "pnl", "reported", "report_correct", "decide_s", "answer_s", "balance_after", "verdict",
    ]]
    for r in played(session):
        d = r.decision
        rows.append([
            r.number, r.event or "", " ".join(src.label(i) for i in r.items), d.bid, d.ask, round(d.fair, 4),
            d.action, d.size, "" if d.edge_per_unit is None else round(d.edge_per_unit, 4),
            round(d.edge_dollars, 4), r.settle, r.pnl, "" if r.reported is None else r.reported,
            "" if r.report_correct is None else r.report_correct, round(d.t, 2),
            "" if r.answer_time is None else round(r.answer_time, 2), r.balance_after, r.verdict,
        ])
    return rows
