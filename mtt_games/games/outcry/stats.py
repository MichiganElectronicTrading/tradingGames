"""Outcry results, your trade list, history records and CSV rows. Pure Python."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mtt_games.games.outcry.engine import trade_score
from mtt_games.games.outcry.model import knowledge_of

if TYPE_CHECKING:
    from mtt_games.games.outcry.engine import OutcryGame, Trade

YOU = 0
BUY, SELL = "BUY", "SELL"


@dataclass(frozen=True)
class YourTrade:
    trade: Trade
    side: str  # BUY / SELL from your point of view
    counterparty: str
    fair: float  # your exact fair at that moment
    edge_settle: float  # $ vs the settle: (settle − price) × size when buying
    edge_fair: float  # $ vs your fair at the time
    score: int  # +1 made money at the settle, −1 lost, 0 at the settle


@dataclass(frozen=True)
class Row:
    rank: int
    name: str
    number: int
    trades: int
    pnl: int
    style: str | None


@dataclass(frozen=True)
class Results:
    settle: int
    true_range: tuple[int, int]
    range_seen: tuple[int, int]  # what you could see before the final reveal
    leaderboard: list[Row]
    your_trades: list[YourTrade]
    avg_edge_settle: float | None
    avg_edge_fair: float | None
    responses_traded: int
    responses_passed: int
    opens: int  # rounds you were forced to open
    open_fills: int  # responses that traded on your opens
    your_open_width: float | None  # your average opening width (None if you never opened)
    computer_open_width: float | None  # the computer openers' average opening width this game
    last_prices: list[tuple[int, int | None]]  # (round, last trade price)
    best: YourTrade | None
    worst: YourTrade | None
    pnl: int
    score: int  # your net trade score (what you report)
    reported: int | None
    report_correct: bool
    report_seconds: float | None


def your_trades(game: OutcryGame, seat: int = YOU) -> list[YourTrade]:
    out = []
    for t in game.trades:
        if seat not in (t.buyer, t.seller):
            continue
        buying = t.buyer == seat
        sign = 1 if buying else -1
        fair = game.fair_in_round(seat, t.round)
        out.append(YourTrade(
            trade=t, side=BUY if buying else SELL, counterparty=game.names[t.seller if buying else t.buyer],
            fair=fair, edge_settle=sign * (game.settle - t.price) * t.size, edge_fair=sign * (fair - t.price) * t.size,
            score=trade_score(buying, t.price, game.settle),
        ))
    return out


def grouped(trades: list[YourTrade]) -> list[tuple[int, str, str, int, int, int, int]]:
    """Your trade list: (round, kind, side, price, lots, trades, score per trade), consecutive repeats merged
    (same round, kind, side and price — so the same score)."""
    rows: list[list[Any]] = []
    for y in trades:
        t = y.trade
        if rows and rows[-1][:4] == [t.round, t.kind, y.side, t.price]:
            rows[-1][4] += t.size
            rows[-1][5] += 1
        else:
            rows.append([t.round, t.kind, y.side, t.price, t.size, 1, y.score])
    return [tuple(r) for r in rows]


def totals(trades: list[YourTrade]) -> tuple[int, int]:
    """(lots bought, lots sold)."""
    return (sum(y.trade.size for y in trades if y.side == BUY), sum(y.trade.size for y in trades if y.side == SELL))


def reveal_rows(game: OutcryGame) -> list[tuple[int, str | None]]:
    """Every revealed value with its label, in reveal order (anonymous)."""
    return [(r.value, r.label) for r in game.public().reveals]


def results(game: OutcryGame) -> Results:
    n = game.config.players
    pnls = [game.pnl(s) for s in range(n)]
    counts = [sum(1 for t in game.trades if s in (t.buyer, t.seller)) for s in range(n)]
    order = sorted(range(n), key=lambda s: (-pnls[s], s))
    board = [
        Row(1 + sum(1 for q in range(n) if pnls[q] > pnls[s]), game.names[s], game.setup.numbers[s], counts[s],
            pnls[s], game.setup.styles[s])
        for s in order
    ]
    mine = your_trades(game)
    responses = [x for r in game.rounds for x in r.responses if x.seat == YOU]
    opened = [r for r in game.rounds if r.opener == YOU]
    theirs = [r for r in game.rounds if r.opener != YOU]
    last_prices = []
    for r in game.rounds:
        prices = [t.price for t in game.trades if t.round == r.number]
        last_prices.append((r.number, prices[-1] if prices else None))
    before_final = game.config.rounds  # reveals made before the final screen
    seen = knowledge_of(game.setup, YOU, before_final, game.config.extreme_reveals).range_seen
    return Results(
        settle=game.settle,
        true_range=(game.setup.low, game.setup.high),
        range_seen=seen,
        leaderboard=board,
        your_trades=mine,
        avg_edge_settle=sum(y.edge_settle for y in mine) / len(mine) if mine else None,
        avg_edge_fair=sum(y.edge_fair for y in mine) / len(mine) if mine else None,
        responses_traded=sum(1 for x in responses if x.action in ("buy", "sell") and x.applied),
        responses_passed=sum(1 for x in responses if not (x.action in ("buy", "sell") and x.applied)),
        opens=len(opened),
        open_fills=sum(1 for r in opened for x in r.responses if x.action in ("buy", "sell") and x.applied),
        your_open_width=sum(r.ask - r.bid for r in opened) / len(opened) if opened else None,
        computer_open_width=sum(r.ask - r.bid for r in theirs) / len(theirs) if theirs else None,
        last_prices=last_prices,
        best=max(mine, key=lambda y: y.edge_settle) if mine else None,
        worst=min(mine, key=lambda y: y.edge_settle) if mine else None,
        pnl=game.pnl(YOU),
        score=game.score(YOU),
        reported=game.reported,
        report_correct=game.report_correct,
        report_seconds=game.report_seconds,
    )


def history_record(game: OutcryGame, when: datetime | None = None) -> dict[str, Any]:
    """One JSON line per game. `final_balance` holds your P&L and `edge_taken` your total edge vs your own
    fair, so the shared Stats screen reads it unchanged."""
    mine = your_trades(game)
    return {
        "game": game.source.key,
        "ts": (when or datetime.now()).isoformat(timespec="seconds"),
        "mode": game.mode,
        "seed": game.seed,
        "config": game.config.to_dict(),
        "rounds_played": len(game.rounds),
        "pnl": game.pnl(YOU),
        "score": game.score(YOU),
        "final_balance": game.pnl(YOU),
        "edge_taken": round(sum(y.edge_fair for y in mine), 4),
        "trades": len(mine),
        "reports_correct": int(game.report_correct),
        "reports_total": 1,
        "avg_answer_s": game.report_seconds,
        "ended_early": False,
        "end_reason": None,
    }


def csv_rows(game: OutcryGame) -> list[list[Any]]:
    """The full tape: one row per trade, with your side and your fair when you were in it."""
    rows: list[list[Any]] = [[
        "round", "kind", "t_s", "buyer", "seller", "price", "size", "aggressor", "your_side", "your_fair", "settle",
    ]]
    for t in game.trades:
        start = game.rounds[t.round - 1].outcry_start
        t_s = 0.0 if t.kind == "open" or start is None else (t.at - start) * game.TICK
        side = BUY if t.buyer == YOU else SELL if t.seller == YOU else ""
        fair = round(game.fair_in_round(YOU, t.round), 4) if side else ""
        rows.append([t.round, t.kind, t_s, game.names[t.buyer], game.names[t.seller], t.price, t.size,
                     game.names[t.aggressor], side, fair, game.settle])
    return rows

