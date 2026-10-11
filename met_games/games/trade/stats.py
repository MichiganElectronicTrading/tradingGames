"""Trading Game recap math, mistakes, history records and CSV rows. Pure Python."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from met_games.games.sumgame.engine import BUY, SELL, TIMEOUT
from met_games.games.sumgame.stats import money
from met_games.games.trade.engine import PLAYERS, YOU, Action, Hand, TradeSession, Turn


def edge(a: Action, turn: Turn) -> float:
    """Your expected $ on a take vs table_fair: buying = fair − ask, selling = bid − fair, × size."""
    if a.action == BUY:
        return (a.table_fair - a.price) * a.size
    if a.action == SELL:
        return (a.price - a.table_fair) * a.size
    return 0.0


def your_takes(hand: Hand) -> list[tuple[Turn, Action]]:
    return [(t, a) for t in hand.turns if t.maker != YOU for a in t.fills if a.who == YOU]


def peeker_units(hand: Hand) -> int:
    """Units traders who peeked took off your market."""
    turn = hand.your_turn()
    return sum(a.size for a in turn.fills if hand.peeks.get(a.who) is not None)


def market_label(turn: Turn) -> str:
    return "—" if not turn.posted else f"{turn.bid} @ {turn.ask} ×{turn.size}"


def settled(session: TradeSession) -> list[Hand]:
    return [h for h in session.hands if h.settled]


@dataclass(frozen=True)
class SessionStats:
    start_balance: int
    final_balance: int
    making: int
    taking: int
    edge_taken: float  # expected $ of your takes vs table_fair
    reports_correct: int
    reports_total: int
    avg_answer_s: float | None
    hands_played: int

    @property
    def change(self) -> int:
        return self.final_balance - self.start_balance


def session_stats(session: TradeSession) -> SessionStats:
    hands = settled(session)
    reported = [h for h in hands if h.reported is not None]
    times = [h.answer_time for h in reported if h.answer_time is not None]
    return SessionStats(
        start_balance=session.config.budget,
        final_balance=session.balance,
        making=sum(h.making_pnl for h in hands),
        taking=sum(h.taking_pnl for h in hands),
        edge_taken=sum(edge(a, t) for h in hands for t, a in your_takes(h)),
        reports_correct=sum(1 for h in reported if h.report_correct),
        reports_total=len(reported),
        avg_answer_s=sum(times) / len(times) if times else None,
        hands_played=len(hands),
    )


def standings(session: TradeSession) -> list[tuple[int, str, int]]:
    """(rank, player, cumulative P&L), best first; ties share a rank."""
    totals = session.totals
    order = sorted(PLAYERS, key=lambda p: -totals[p])
    return [(1 + sum(1 for q in PLAYERS if totals[q] > totals[p]), p, totals[p]) for p in order]


def mistakes(session: TradeSession) -> list[str]:
    out: list[str] = []
    for h in settled(session):
        mine = h.your_turn()
        if mine.timed_out:
            out.append(f"H{h.number}: quote timer ran out — you posted no market")
        if h.making_pnl < 0:
            units = peeker_units(h)
            out.append(
                f"H{h.number}: your market lost {money(h.making_pnl)} — traders who peeked took {units} "
                f"unit{'s' * (units != 1)} off you"
            )
        for t in h.turns:
            if t.maker == YOU:
                continue
            a = t.action_of(YOU)
            if a is None:
                continue
            if a.is_fill and edge(a, t) < 0:
                verb = "bought" if a.action == BUY else "sold"
                out.append(
                    f"H{h.number} T{t.number}: {verb} {a.size} @ {a.price} on {t.maker}'s market vs table fair "
                    f"{a.table_fair:.2f} — edge {money(edge(a, t), 2)}"
                )
            if a.action == TIMEOUT:
                out.append(f"H{h.number} T{t.number}: timed out on {t.maker}'s market")
        if h.reported is not None and not h.report_correct:
            out.append(f"H{h.number}: reported P&L {h.reported}, actual {h.pnl(YOU)}")
    return out


def bankroll(session: TradeSession) -> list[int]:
    return [session.config.budget] + [h.balance_after for h in settled(session)]


def history_record(session: TradeSession, when: datetime | None = None) -> dict[str, Any]:
    """One JSON line per session. Keys match the sum games' so the shared Stats screen reads it."""
    s = session_stats(session)
    return {
        "game": session.source.key,
        "ts": (when or datetime.now()).isoformat(timespec="seconds"),
        "mode": session.mode,
        "seed": session.seed,
        "config": session.config.to_dict(),
        "rounds_played": s.hands_played,
        "start_balance": s.start_balance,
        "final_balance": s.final_balance,
        "making": s.making,
        "taking": s.taking,
        "edge_taken": round(s.edge_taken, 4),
        "realized": s.change,
        "reports_correct": s.reports_correct,
        "reports_total": s.reports_total,
        "avg_answer_s": None if s.avg_answer_s is None else round(s.avg_answer_s, 2),
        "standings": dict(session.totals),
        "ended_early": False,
        "end_reason": None,
    }


def csv_rows(session: TradeSession) -> list[list[Any]]:
    """One row per action (every taker on every market), with the hand's deal and settle."""
    rows: list[list[Any]] = [[
        "hand", "event", "cards", "settle", "turn", "maker", "bid", "ask", "size", "taker", "action", "fill_size",
        "price", "table_fair", "your_pnl", "your_hand_pnl", "reported", "report_correct",
    ]]
    for h in settled(session):
        cards = " ".join(str(c) for c in h.items)
        for t in h.turns:
            if not t.actions:  # a market that was never posted
                rows.append([
                    h.number, h.event or "", cards, h.settle, t.number, t.maker, "", "", 0, "", "no market", 0, "",
                    "", 0, h.pnl(YOU), "" if h.reported is None else h.reported,
                    "" if h.report_correct is None else h.report_correct,
                ])
            for a in t.actions:
                rows.append([
                    h.number, h.event or "", cards, h.settle, t.number, t.maker, t.bid, t.ask, t.size, a.who, a.action,
                    a.size, "" if a.price is None else a.price, round(a.table_fair, 4), h.fill_pnl(t, a),
                    h.pnl(YOU), "" if h.reported is None else h.reported,
                    "" if h.report_correct is None else h.report_correct,
                ])
    return rows
