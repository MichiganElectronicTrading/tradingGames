"""ETF Arb UI spec: banner, Custom rows, how-to text, and the hook into its own screens.
The lobby, custom, how-to and stats screens are the shared sum-game ones."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from textual.screen import Screen

from mtt_games.games.etf.config import EVENT_FREQS, freq_label
from mtt_games.games.etf.engine import EtfGame
from mtt_games.games.etf.traders import MARGIN
from mtt_games.games.sumgame.screens.custom import Field
from mtt_games.games.sumgame.ui import GameUI, register

D = Decimal
BANNER = """\
███████ ████████ ███████
██         ██    ██
█████      ██    █████
██         ██    ██
███████    ██    ██
A R B I T R A G E"""

SUBTITLE = "price the basket · trade the gap · beat the traders to it"
LOBBY_NOTE = "NAV = Σ weight × price · buy if NAV > ask · sell if NAV < bid · skip if the gap won't cover the fee"


def _steps(lo: Any, hi: Any, inc: Any = 1) -> Any:
    return lambda v, d: max(lo, min(hi, v + d * inc))


def _cycle(options: tuple) -> Any:
    return lambda v, d: options[max(0, min(len(options) - 1, options.index(v) + d))]


def _on_off(v: bool) -> str:
    return "on" if v else "off"


def _toggle(v: bool, d: int) -> bool:
    return d > 0


def custom_fields() -> list[Field]:
    secs = lambda v: f"{v:g}s"  # noqa: E731
    return [
        Field("stocks", "stocks", "basket size", _steps(2, 10)),
        Field("weight_places", "weights", "tenths or hundredths", _cycle((1, 2)),
              lambda v: {1: "tenths", 2: "hundredths"}[v]),
        Field("price_places", "prices", "whole, tenths or cents", _cycle((0, 1, 2)),
              lambda v: {0: "whole", 1: "tenths", 2: "cents"}[v]),
        Field("rounds", "rounds", "1–20", _steps(1, 20)),
        Field("timer_s", "timer", "per round, s", _steps(3, 120), secs),
        Field("size", "size at bid/ask", "units, shared", _steps(1, 200, 5)),
        Field("skip_chance", "skip-round chance", "small-gap rounds",
              lambda v, d: round(max(0.0, min(1.0, v + d * 0.01)), 2), lambda v: f"{v:.0%}"),
        Field("gap_min", "trade gap from", "|gap|, trade rounds", _steps(D("0.46"), D(10), D("0.05")),
              lambda v: f"{v:.2f}"),
        Field("gap_max", "trade gap to", "|gap|, trade rounds", _steps(D("0.46"), D(10), D("0.05")),
              lambda v: f"{v:.2f}"),
        Field("trader_sd", "trader error sd", "NAV error, $", _steps(D(0), D(10), D("0.05")), lambda v: f"{v:.2f}"),
        Field("decide_min", "decide from", "trader decision, s", _steps(0.0, 120.0, 0.5), secs),
        Field("decide_max", "decide to", "trader decision, s", _steps(0.0, 120.0, 0.5), secs),
        Field("events", "events", "splits, rebalances", _toggle, _on_off),
        Field("event_freq", "event freq", "rounds with an event", _cycle(EVENT_FREQS), freq_label),
        Field("trap_skill", "trader event skill", "applies events right", lambda v, d: round(max(0.0, min(1.0, v + d * 0.05)), 2),
              lambda v: f"{v:.0%}"),
        Field("fee", "fee", "$ per trade", _steps(D(0), D(100), D(1)), lambda v: f"${v:g}"),
        Field("bonus", "first bonus", "of (gross − fee)", _steps(D(0), D(1), D("0.05")), lambda v: f"{v * 100:g}%"),
        Field("max_units", "max units", "per trade", _steps(1, 100)),
        Field("seed", "seed", "random = new each time",
              lambda v, d: (1 if d > 0 else None) if v is None else (None if v + d < 1 else v + d),
              lambda v: "random" if v is None else str(v)),
    ]


def howto() -> list[tuple[str, list[str]]]:
    return [
        ("THE BASKET", [
            "Each game uses one fixed basket of stocks with fixed weights (whole tenths on EASY, hundredths "
            "otherwise; they add up to exactly 1). The ETF's fair value is its NAV = Σ weight × price.",
            "Prices are whole dollars on EASY, tenths on MEDIUM and cents on HARD. Every round they move a "
            "little (about 1 in 5 don't move; more on EASY, where small moves round away). CHG and % show the move "
            "since the last round. The W × P column is filled in, rounded to the same precision as the prices; "
            "NAV is the sum of that column, and adding it up is your job.",
            "Shortcut: the BASKET title shows last round's NAV, and Δ W × P shows how much each row's W × P moved, "
            "so last NAV + Σ Δ W × P = this round's NAV exactly. (CHG is the stock's own price move; summing CHG "
            "doesn't work — NAV moves by weight × CHG.)",
        ]),
        ("THE QUOTE", [
            "An ETF bid/ask is posted somewhere around NAV, quoted at the same precision as the prices: $1 wide "
            "in whole dollars on EASY, 0.2 wide in tenths on MEDIUM, 0.20 wide in cents on HARD. Buy at the ask if "
            "NAV > ask, sell at the "
            "bid if NAV < bid, or skip. Some rounds the gap is too small to be worth it — about 1 in 6 on EASY, "
            "1 in 5 on MEDIUM and 1 in 4 on HARD.",
            "Everyone trades against the same limited size at each side (40 / 30 / 20 units). Each trade uses "
            "units up; an empty side can't be traded.",
        ]),
        ("A ROUND", [
            "You get one trade per round — BUY n @ ask, SELL n @ bid (1–20 units, capped by what's left) — or "
            "SKIP. The timer running out is a skip. Three computer traders, KESTREL, OSPREY and MERLIN, race you.",
        ]),
        ("P&L", [
            "P&L settles at the round's NAV. Buy: (NAV − ask) × units. Sell: (bid − NAV) × units. Every trade "
            "pays a flat $10 fee. The first trade of the round, by anyone, earns +20% of (gross − fee) when that "
            "is positive.",
            "Example: NAV 237.50, buy 10 @ 233.40 → gross (237.50 − 233.40) × 10 = $41.00, fee −$10.00, and if "
            "you were first, bonus 20% of $31.00 = +$6.20 → net +$37.20.",
            "At n units you need a gap over $10 / n per unit just to cover the fee: 20 units need over $0.50.",
            "The right call (for scoring) uses u = 20 units (or the size, if smaller): BUY if (NAV − ask) × u > "
            "10, SELL if (bid − NAV) × u > 10, else SKIP.",
        ]),
        ("MARKET EVENTS (HARD)", [
            "In about 1 round in 3, a split, reverse split or rebalance hits one stock. An amber banner explains "
            "it and the row is marked ⚑ — but the table does NOT update the weight. You must:",
            "N-for-1 split: the price shown is post-split; use weight × N.  1-for-N reverse split: use "
            "weight ÷ N.  Rebalance: use the new weight from the banner. The ⚑ row's W × P (amber) is still "
            "computed from the stale weight, so fix that cell yourself. From the next round on the table "
            "shows the adjusted weight.",
        ]),
        ("THE COMPUTER TRADERS", [
            "Each prices the basket with a noisy NAV (error sd $1.00 / $0.30 / $0.10 by difficulty) and decides "
            "once, at a time drawn from its window (11–20 s / 7–14 s / 2–7 s). It trades the side its gap points "
            f"to, min(20, units left), only if gap × units > fee + ${MARGIN:g}. On event rounds it applies the "
            "event correctly 70% of the time; otherwise it falls for the trap.",
        ]),
        ("CONTROLS", [
            "B buy · S sell · K skip · ←→ units ±1 · shift+←→ ±5 · ⏎ skip ahead once you've acted · Esc quit "
            "to the lobby.",
            "Result: ⏎ next round. Recap: R replay seed · N next difficulty · E export CSV · L lobby · Q quit.",
        ]),
    ]


def first_screen(game: EtfGame) -> Screen:
    from mtt_games.games.etf.screens import screen_for

    return screen_for(game)


ETF_UI = register(GameUI(
    session_cls=EtfGame,
    banner=BANNER,
    tagline="basket arbitrage race",
    make_widget=None,  # type: ignore[arg-type]  (no dealt items to draw)
    setup_rules=(),
    fair_rules=(),
    custom_fields=custom_fields,
    howto=howto,
    first_screen=first_screen,
    subtitle=SUBTITLE,
    lobby_note=LOBBY_NOTE,
))
