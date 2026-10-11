"""Trading Game UI spec: banner, Custom rows, how-to-play text, and the hook into its own screens.
The lobby, custom, how-to and stats screens are the shared sum-game ones."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from textual.screen import Screen

from met_games.games.card.ui import card_widget
from met_games.games.sumgame.config import freq_label
from met_games.games.sumgame.screens.custom import Field, fields_for
from met_games.games.sumgame.ui import GameUI, register
from met_games.games.trade.config import PEEKS, TradeConfig, peeks_label
from met_games.games.trade.engine import TRADER_SIZE, TradeSession

BANNER = """\
████████ ██████   █████  ██████  ███████
   ██    ██   ██ ██   ██ ██   ██ ██
   ██    ██████  ███████ ██   ██ █████
   ██    ██   ██ ██   ██ ██   ██ ██
   ██    ██   ██ ██   ██ ██████  ███████"""


def _steps(lo: int, hi: int) -> Any:
    return lambda v, d: max(lo, min(hi, v + d))


def custom_fields() -> list[Field]:
    """Custom rows: Card's deal fields plus the trading game's own (labels say what they mean here)."""
    base = {f.key: f for f in fields_for(TradeConfig)}
    timer = base["timer_s"]
    width = _steps(1, TradeConfig.SPREAD_MAX)
    return [
        replace(base["n_cards_min"], hint="2–10 dealt per hand"),
        base["n_cards_max"],
        base["face_up_min"],
        base["face_up_max"],
        replace(base["rounds"], label="hands", hint="1–20"),
        Field("quote_timer_s", "quote timer", "5–120 s, your market", timer.step, timer.show),
        replace(timer, label="take timer", hint="5–120 s, their markets"),
        Field("width_min", "width min", "your ask − bid, from", width),
        Field("width_max", "width max", "your ask − bid, up to", width),
        replace(
            base["sizing"], label="quote size", hint=f"fixed {TradeConfig.FIXED_SIZE} or choose",
            show=lambda v: f"fixed {TradeConfig.FIXED_SIZE}" if v == "fixed" else f"1–{TradeConfig.SIZE_MAX}",
        ),
        replace(base["spread"], label="trader width", hint="computer ask − bid, 1–8"),
        Field("peeks", "peeks", "traders who peek", lambda v, d: PEEKS[max(0, min(1, PEEKS.index(v) + d))],
              peeks_label),
        replace(base["mid_round_flip"], label="turn flips", hint="a hidden card turns up"),
        Field("learn_rate", "learn rate", "traders learn from fills",
              lambda v, d: round(max(0.0, min(1.0, v + d * 0.05)), 2), lambda v: f"{v:g}"),
        base["budget"],
        replace(base["event_freq"], show=lambda v: freq_label(v).replace("round", "hand")),
        base["seed"],
    ]


def howto() -> list[tuple[str, list[str]]]:
    return [
        ("THE TABLE", [
            "You and three computer traders — DELTA, GAMMA, THETA — sit at a table. Each hand is ONE deal of "
            "cards (2–10 face value, J=11, Q=12, K=13, A=14). Some are face up; the rest stay hidden.",
            "The hand settles at the sum of ALL the cards (after any market event).",
        ]),
        ("A HAND: FOUR TURNS", [
            "The seat order is shuffled every hand. On turn i the player in seat i makes a two-way market "
            "(BID @ ASK, a size per side) and the other three may trade it. Everyone makes exactly once.",
            "Same cards for all four turns. Your position and cash carry from turn to turn.",
            "After turn 4 the cards flip and every position settles: hand P&L = cash + position × settle. "
            "The game is zero-sum — the four hand P&Ls always add up to $0.",
        ]),
        ("YOUR MARKET", [
            "Type BID, ASK and SIZE, then ⏎ to show it. Your width (ask − bid) must be inside the mode's "
            "allowed range. Easy fixes the size at 5; otherwise it's 1–10 per side.",
            "The traders then act on it in seat order. If the quote timer runs out you post nothing and the "
            "turn passes with no trades.",
        ]),
        ("THEIR MARKETS", [
            "When a trader makes, you act first: buy at the ask, sell at the bid (up to what's left on that "
            "side), or pass. The other traders trade after you. Take-timer expiry is a pass.",
        ]),
        ("HOW THE TRADERS THINK", [
            "Each trader may have peeked at one hidden card (Medium/Hard: all three, at different cards when "
            "there are 3+ hidden; Easy: only one random trader). Its private fair is the exact expected sum "
            "given the face-up cards plus that peeked card.",
            "est = private fair + a learned offset, clamped to the settle range.",
            "As maker: mid = public fair + ½ × (est − public fair), bid = round(mid − w/2), ask = bid + w, "
            f"size {TRADER_SIZE} per side (w = the mode's trader width).",
            f"As taker: buy up to {TRADER_SIZE} at the ask if est ≥ ask + 1, sell at the bid if est ≤ bid − 1, "
            "else pass. So a trader that buys your ask is telling you it thinks the sum is higher.",
            "Hard only: after every fill each trader moves its offset 25% of the way toward the fill's signal "
            "(price + 1 after a buy, price − 1 after a sell). Easy and Medium traders never learn — that's "
            "exploitable, and exploiting it is the lesson.",
        ]),
        ("YOUR RISK", [
            "Your P&L is linear in the settle, so the worst case is at the lowest or highest possible sum. "
            "Anything you do must keep that worst-case hand loss within your balance: a quote is checked as "
            "if all the bid fills, all the ask fills, and both fill; a take is capped to the size that fits, "
            "and a side that can't take 1 unit is disabled. The traders have no budget limit.",
        ]),
        ("SETTLE & REPORT", [
            "At settle you type your hand P&L (an exact integer). Reporting never changes your balance. "
            "W walks through the math with the hand's real numbers.",
            "Making P&L = your P&L from fills on your own market; taking P&L = from your trades on theirs. "
            "Table fair (face-up cards plus every peeked card) is the yardstick for edge and mistakes.",
        ]),
        ("HARD MODE", [
            "Between turns 1→2, 2→3 and 3→4 one random hidden card turns face up (never the last one), and "
            "fair and the range update. A market event is announced every hand.",
        ]),
        ("CONTROLS", [
            "Your market: type digits (− for negatives) · Tab next field · ⏎ show market.",
            "Their market: B buy · S sell · P pass · ←→ size ±1 · ⏎ next turn after you act.",
            "Fills: ⏎ skip the feed, ⏎ again to continue.",
            "Settle: type P&L + ⏎ · W walkthrough · ⏎ next hand.",
            "Recap: R replay same seed · N next difficulty · E export CSV · L lobby · Q quit.",
        ]),
    ]


def first_screen(session: Any) -> Screen:
    from met_games.games.trade.screens.common import next_screen

    return next_screen(session)


TRADE_UI = register(GameUI(
    session_cls=TradeSession,
    banner=BANNER,
    tagline="market-making drill · you + 3 traders",
    make_widget=card_widget,
    setup_rules=(),
    fair_rules=(),
    custom_fields=custom_fields,
    howto=howto,
    first_screen=first_screen,
))
