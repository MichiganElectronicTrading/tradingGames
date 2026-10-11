"""Outcry UI spec: banner, Custom rows, how-to and COMMANDS text, and the hook into its own screens.
The lobby, custom, how-to and stats screens are the shared sum-game ones."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.outcry.commands import CHEAT_SHEET
from met_games.games.outcry.config import HELPER_LABELS, HELPERS, STYLE_FIELDS, STYLES
from met_games.games.outcry.engine import OutcryGame
from met_games.games.outcry.traders import (
    CHASE,
    OPEN_WIDTHS,
    LEARN_RATE,
    MAKER_WIDTH,
    PASSIVE_EDGE,
    PASSIVE_SLOW,
    PASSIVE_WIDTH,
    SNIPER_EDGE,
)
from met_games.games.sumgame.screens.custom import Field
from met_games.games.sumgame.ui import GameUI, register
from met_games.widgets import AMBER, KeyBar, TopBar

BANNER = """\
 ██████  ██    ██ ████████  ██████ ██████  ██    ██
██    ██ ██    ██    ██    ██      ██   ██  ██  ██
██    ██ ██    ██    ██    ██      ██████    ████
██    ██ ██    ██    ██    ██      ██   ██    ██
 ██████   ██████     ██     ██████ ██   ██    ██"""

SUBTITLE = "8 hidden numbers · 1 contract · settles at the sum of all 8"


def _steps(lo: int, hi: int, inc: int = 1) -> Any:
    return lambda v, d: max(lo, min(hi, v + d * inc))


def _halves(lo: float, hi: float, inc: float) -> Any:
    return lambda v, d: max(lo, min(hi, v + d * inc))


def _cycle(options: tuple) -> Any:
    return lambda v, d: options[max(0, min(len(options) - 1, options.index(v) + d))]


def _on_off(v: bool) -> str:
    return "on" if v else "off"


def custom_fields() -> list[Field]:
    seconds = lambda v: f"{v}s"  # noqa: E731
    fields = [
        Field("players", "players", "4–10 at the table", _steps(4, 10)),
        Field("rounds", "rounds", "≤ players − 1", _steps(1, 9)),
        Field("respond_s", "respond timer", "respond / open, s", _steps(3, 120), seconds),
        Field("outcry_s", "outcry", "open outcry, s", _steps(5, 300, 5), seconds),
        Field("report_s", "report timer", "trade score, s", _steps(10, 300, 5), seconds),
        Field("trade_size", "trade size", "lots per order, 1–5", _steps(1, 5)),
        Field("limit", "limit", "position limit ±, 10–50", _steps(10, 50, 5), lambda v: f"±{v}"),
        Field("helper", "helper panel", "WHAT YOU KNOW", _cycle(HELPERS), lambda v: HELPER_LABELS[v].split(" +")[0]),
    ]
    fields += [Field(f, f"{s.lower()}s", f"{s} traders", _steps(0, 9)) for f, s in zip(STYLE_FIELDS, STYLES)]
    fields += [
        Field("cooldown_min", "cooldown min", "per trader, s", _halves(0.5, 60, 0.5), lambda v: f"{v:g}s"),
        Field("cooldown_max", "cooldown max", "per trader, s", _halves(0.5, 60, 0.5), lambda v: f"{v:g}s"),
        Field("pace_s", "pace cap", "1 computer action per", _halves(0.25, 10, 0.25), lambda v: f"{v:g}s"),
        Field("learns", "learn tape", "traders follow trades", lambda v, d: d > 0, _on_off),
        Field("extreme_reveals", "extreme sched", "lowest/highest reveals", lambda v, d: d > 0, _on_off),
        Field("seed", "seed", "random = new each time",
              lambda v, d: (1 if d > 0 else None) if v is None else (None if v + d < 1 else v + d),
              lambda v: "random" if v is None else str(v)),
    ]
    return fields


def commands_section() -> tuple[str, list[str]]:
    return ("COMMANDS", [
        "Type on the command line during the open outcry, then ⏎:",
        "b 464 — bid 464 · o 467 — offer 467 · 464 @ 467 — bid and offer at once",
        "buy — lift the best offer · sell — hit the best bid (an error if there's none)",
        "x — cancel all · xb — cancel your bid · xo — cancel your offer",
        "↑ recalls your last command · Ctrl+B / Ctrl+S = buy / sell · Esc cancels all",
        "A new bid or offer replaces your old one on that side. Bad input shows an error and is never sent; "
        "every command echoes a ✓ or ✗ line.",
        f"cheat sheet: {CHEAT_SHEET}",
    ])


def howto() -> list[tuple[str, list[str]]]:
    lo, hi = MAKER_WIDTH
    plo, phi = PASSIVE_WIDTH
    return [
        ("THE SETUP", [
            "Eight players — you and 7 computer traders — each hold one hidden number. Every number is an "
            "independent uniform whole number in a hidden range [L, U], where L < U are drawn from 0–100 with "
            "U − L ≥ 10. You see only your own number. One contract settles at the SUM of all eight.",
        ]),
        ("A ROUND", [
            "1. Forced open: a random player (maybe you) must quote bid @ ask, one lot each way, at any width: "
            "bid ≥ 0, ask ≤ 800 (the highest possible settle) and ask > bid. If your timer runs out the game "
            "quotes your last outcry mid ± 5 for you (400 ± 5 if you have none).",
            "2. Forced response: everyone else buys at the ask, sells at the bid, or passes — blind and at once. "
            "Responses that would breach a position limit are skipped and logged.",
            "3. Open outcry: a live order book for the round's duration. One bid and one offer each; price-time "
            "priority; no self-trades; everything is cancelled at the close.",
            "4. Reveal: one hidden number turns over, anonymously. Only its owner knows it was theirs.",
        ]),
        ("THE REVEALS", [
            "The LOWEST number is revealed after round 2 and the HIGHEST after round 5 (a coin flip can swap "
            "them), and they're labeled. Every other reveal is a random hidden number that is NOT an extreme — "
            "so an unlabeled reveal also tells you the lowest and highest are still out there.",
            "After round 7 the last number turns over, you score your own trades, and then the owners, the "
            "true range and the leaderboard are revealed.",
        ]),
        ("EXACT FAIR VALUE", [
            "Fair = E[sum of all eight | what you know]: your number, every reveal, which reveal was yours, and "
            "the LOWEST/HIGHEST labels. The game computes it exactly by weighing every possible hidden range "
            "and every possible set of unknown numbers, including what the reveal rule implies. It's the "
            "yardstick for your edge, the EASY helper panel, and every computer trader.",
        ]),
        ("THE COMPUTER TRADERS", [
            "Each prices the contract from its own exact fair (its own number and the public reveals) and acts "
            "after a random cooldown (EASY 6–10 s · MEDIUM 3–6 s · HARD 1–3 s). The whole table is paced: at "
            "most one computer action (post, replace, cancel or take) per 1.5 s · 0.75 s · 0.25 s, with waiting "
            "traders taking turns. You are never limited. Styles are hidden until the results:",
            f"MAKER keeps a two-sided quote {lo}–{hi} wide around its estimate and requotes after trading or "
            "when its estimate moves.",
            f"SNIPER takes the best price when it's ≥ {SNIPER_EDGE} better than its estimate; otherwise idle.",
            f"PASSIVE quotes wide ({plo}–{phi}), acts {PASSIVE_SLOW:g}× slower, and only takes at ≥ {PASSIVE_EDGE} "
            "better.",
            f"CHASER moves its estimate {CHASE:.0%} toward the last trade price before quoting or taking.",
            "ANCHOR (the dumb money) estimates 8 × the mean of the numbers it knows, ignoring range logic.",
            "As forced opener a trader quotes around its estimate, width by style: "
            + " · ".join(f"{s} {lo}–{hi}" for s, (lo, hi) in OPEN_WIDTHS.items()) + ".",
            f"As forced responder a trader buys if estimate ≥ ask + 1 "
            f"and sells if ≤ bid − 1. On HARD every trader moves {LEARN_RATE:.0%} toward each new trade price.",
        ]),
        commands_section(),
        ("SCORING", [
            "At the end you score your own trades: +1 for each trade that made money at the settle (bought "
            "below / sold above), −1 for each that lost, 0 for one exactly at the settle — one trade, one score, "
            "whatever its size. Enter the net score (an integer, negatives allowed) within 30 s; a timeout "
            "counts as wrong.",
            "The leaderboard still ranks everyone by dollar P&L = cash + position × settle (the eight P&Ls sum to "
            "zero). The results show your edge per trade vs the settle and vs YOUR OWN fair at the moment you "
            "traded — the real skill metric.",
        ]),
    ]


class CommandsScreen(Screen):
    """The lobby's COMMANDS page."""

    BINDINGS = [Binding("escape", "app.pop_screen", "back"), Binding("q", "app.pop_screen", "back", show=False)]

    DEFAULT_CSS = """
    CommandsScreen #commands-scroll { height: 1fr; margin: 0 1; border: double #3FA7B5; border-title-color: #5FD4E0;
                                      border-title-style: bold; padding: 0 1; }
    """

    def __init__(self, ui: GameUI) -> None:
        super().__init__()
        self.ui = ui

    def compose(self) -> ComposeResult:
        yield TopBar(f"{self.ui.crumb} ▸ COMMANDS")
        title, paras = commands_section()
        text = Text(title, style=f"bold {AMBER}")
        for p in paras:
            text.append("\n" + p)
        scroll = VerticalScroll(Static(text), id="commands-scroll")
        scroll.border_title = "COMMANDS"
        yield scroll
        yield KeyBar([("↑↓", "scroll"), ("Esc", "back")])


def first_screen(game: OutcryGame) -> Screen:
    from met_games.games.outcry.screens import screen_for

    return screen_for(game)


OUTCRY_UI = register(GameUI(
    session_cls=OutcryGame,
    banner=BANNER,
    tagline="open outcry · 8 players",
    make_widget=None,  # type: ignore[arg-type]  (no dealt items to draw)
    setup_rules=(),
    fair_rules=(),
    custom_fields=custom_fields,
    howto=howto,
    first_screen=first_screen,
    subtitle=SUBTITLE,
    menu_extras=(("COMMANDS", CommandsScreen),),
))
