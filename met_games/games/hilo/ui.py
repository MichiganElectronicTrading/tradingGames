"""Higher or Lower UI spec: banner, Custom rows, how-to text, and the hooks into its own screens.
Custom and how-to are the shared screens; the lobby is Hi-Lo's own (deck picker, high scores)."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.screen import Screen

from met_games.games.hilo.config import BOARD_LABELS, BOARDS, DECK_LABELS, DECKS, HiloConfig
from met_games.games.hilo.engine import HiloGame
from met_games.games.sumgame.screens.custom import Field
from met_games.games.sumgame.ui import GameUI, register
from met_games.widgets import AMBER, DIM, GREEN, RED, TEXT

BANNER = """\
██   ██ ██     ██       ██████
██   ██ ██     ██      ██    ██
███████ ██     ██      ██    ██
██   ██ ██     ██      ██    ██
██   ██ ██     ███████  ██████"""

SUBTITLE = "call it · size it · fast"

# The scoring rules, one per row: (name, name style, description, value, value style). None is the divider.
# The lobby's SCORING panel renders these; the how-to screen can reuse them.
SCORING_ROWS: list[tuple[str, str, str, str, str] | None] = [
    ("PERFECT", f"bold {GREEN}", "stake within 10% of right size", "100", TEXT),
    ("GOOD", GREEN, "within 25%", "60", TEXT),
    ("OK", TEXT, "right side, sizing off", "20", TEXT),
    ("DISCIPLINE", AMBER, "no edge, bet 0", "50", TEXT),
    ("SAT OUT", RED, "edge, but bet 0", "0 · combo reset", RED),
    ("MISS", RED, "wrong side or no-edge bet", "0 · combo reset", RED),
    None,
    ("LIGHTNING", AMBER, "first 25% of clock", "×2.0", TEXT),
    ("FAST", AMBER, "first 50% of clock", "×1.5", TEXT),
    ("COMBO", AMBER, "+0.1 per GOOD+ in a row", "up to ×3.0", TEXT),
    ("END BONUS", AMBER, "1000 × log₂(final ÷ start)", "+ bonus", TEXT),
    ("BUST", RED, "capital under 1", "game over", RED),
]
SPEED_ROWS = ("LIGHTNING", "FAST")  # timed bets only
SCORING_NOTE = "speed bonus only on PERFECT / GOOD / DISCIPLINE · OK keeps the streak"
SCORING_NOTE_UNTIMED = "OK keeps the streak"


def scoring_rows(timed: bool) -> list[tuple[str, str, str, str, str] | None]:
    """SCORING_ROWS, without the speed rows when bets are untimed."""
    return [r for r in SCORING_ROWS if timed or r is None or r[0] not in SPEED_ROWS]


def scoring_table(timed: bool = False) -> Group:
    """The scoring rows as a two-column table (rule left, value right) plus the footnote. Nothing wraps: a
    description that doesn't fit is cut with …"""
    shown = scoring_rows(timed)
    rows = [r for r in shown if r]
    name_w = max(len(r[0]) for r in rows)
    value_w = max(len(r[3]) for r in rows)
    t = Table(show_header=False, show_edge=False, box=None, padding=(0, 1), pad_edge=False, expand=True)
    t.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    t.add_column(justify="right", no_wrap=True)
    for row in shown:
        if row is None:
            t.add_row(Text("─" * 200, style=DIM, overflow="crop"), Text("─" * value_w, style=DIM))
            continue
        name, name_style, desc, value, value_style = row
        rule = Text()
        rule.append(f"{name:<{name_w}}", style=name_style)
        rule.append(f"  {desc}", style=DIM)
        t.add_row(rule, Text(value, style=value_style))
    note = SCORING_NOTE if timed else SCORING_NOTE_UNTIMED
    return Group(t, Text(note, style=DIM, no_wrap=True, overflow="ellipsis"))


def _cycle(options: tuple) -> Any:
    return lambda v, d: options[max(0, min(len(options) - 1, options.index(v) + d))]


def custom_fields() -> list[Field]:
    return [
        Field("deck", "deck", "interview / full / red-black", _cycle(DECKS), lambda v: DECK_LABELS[v]),
        Field("timed", "timed bets", "clock + speed bonus", lambda v, d: d > 0, lambda v: "on" if v else "off"),
        Field("time_s", "time per bet", "2–30 s, timed bets only", lambda v, d: max(2, min(30, v + d)),
              lambda v: f"{v}s"),
        Field("board", "board", "what CARDS LEFT shows", _cycle(BOARDS), lambda v: BOARD_LABELS[v].split(" +")[0]),
        Field("start_capital", "start capital", "100–1,000,000",
              lambda v, d: max(100, min(1_000_000, v + d * (100 if v < 10_000 else 1000))), lambda v: f"{v:,}"),
        Field("quick_lock", "quick lock", "stake key locks the bet", lambda v, d: d > 0, lambda v: "on" if v else "off"),
        Field("seed", "seed", "random = new each time",
              lambda v, d: (1 if d > 0 else None) if v is None else (None if v + d < 1 else v + d),
              lambda v: "random" if v is None else str(v)),
    ]


def custom_note(cfg: HiloConfig) -> str:
    bets = {"interview": 12, "full": 51, "redblack": 52}.get(cfg.deck, "?")
    timing = f"{cfg.time_s}s each" if cfg.timed else "untimed"
    return f"{DECK_LABELS.get(cfg.deck, cfg.deck)} deck · {bets} bets · {timing}"


def howto() -> list[tuple[str, list[str]]]:
    return [
        ("THE GAME", [
            "A card is showing. Call whether the next card is HIGHER or LOWER (A = 1 … K = 13) and stake a whole "
            "percent of your capital at even money: a win adds the stake, a loss takes it, the same rank gives it "
            "back. Cards are not replaced. Capital starts at 1,000 and the stake is floor(capital × % ÷ 100).",
            "Stake 0 is a valid sit-out. If your capital drops below 1 you BUST: the game ends and the remaining "
            "bets and the capital bonus are lost.",
        ]),
        ("DECKS", [
            "Interview: 13 cards, A–K once each — 12 bets. Full: 52 cards — 51 bets. Red/Black: 52 cards with no "
            "values shown — you call the COLOR of every card, 52 bets. EASY defaults to Interview, MEDIUM and HARD "
            "to Full; pick any deck with D in the lobby.",
        ]),
        ("THE RIGHT BET (KELLY)", [
            "Let h = cards left higher than the showing card and l = cards left lower (same rank excluded; for "
            "red/black, h = reds left, l = blacks left). The right side has more cards, and the right stake is "
            "k = |h − l| ÷ (h + l). If h = l there's no edge: the right stake is 0.",
            "Example: a 5 showing on a fresh deck — 32 higher, 16 lower: HIGHER 33%.",
        ]),
        ("GRADES", [
            "Right side, stake s vs k: within max(10% of k, 3 points) → PERFECT 100; within max(25% of k, 7 points) "
            "→ GOOD 60; otherwise OK 20. Wrong side → MISS 0. Sitting out with an edge → SAT OUT 0. No edge: sitting "
            "out → DISCIPLINE 50, betting → MISS. With timed bets on, running out of time → MISS (stake 0).",
        ]),
        ("MULTIPLIERS", [
            "Combo ×(1 + 0.1 × streak), up to ×3. The streak counts PERFECT / GOOD / DISCIPLINE in a row; OK leaves "
            "it alone; MISS and SAT OUT reset it. A bet uses the combo from before its own result.",
            "Bet points = round(base × combo).",
            "Timed bets (a Custom option, off by default) add a clock and a speed multiplier on PERFECT / GOOD / "
            "DISCIPLINE: LIGHTNING ×2 within the first 25% of the bet's clock, FAST ×1.5 within 50%, so bet points "
            "= round(base × speed × combo); a timeout is a stake-0 MISS and resets the streak. Timed and untimed "
            "scores have separate high-score tables.",
        ]),
        ("END OF GAME", [
            "Final score = bet points + capital bonus, where the bonus is round(1000 × log2(final ÷ start)) if you "
            "finished above your start and didn't bust. The end screen compares your multiple with the Kelly "
            "benchmark (staking exactly k every bet on this deck order) and shows your worst bet.",
        ]),
        ("DIFFICULTY", [
            "All three are untimed. EASY: the board shows counts per rank, lower/same/higher and the odds. MEDIUM: "
            "counts and lower/same/higher. HARD: cards left and the last three cards only.",
        ]),
        ("CONTROLS", [
            "H / L or ↑ / ↓ (R / B or ↑ / ↓ on red/black) side · 0–9 stake 0–90% · A all-in · ←→ ±5% · Shift+←→ (or [ ]) to the "
            "previous / next multiple of 25% · ⏎ lock. With quick lock on (the default), 0–9 or A locks the bet as "
            "soon as a side is picked; the arrows never lock. ⏎ skips the reveal flash.",
            "End: R replay deck · N new deck · B review bets · L lobby · Q quit.",
            "Club play: everyone runs met-games hilo --seed N (optionally --deck full) and gets the same deck order.",
        ]),
    ]


def first_screen(game: HiloGame) -> Screen:
    from met_games.games.hilo.screens import screen_for

    return screen_for(game)


HILO_UI = register(GameUI(
    session_cls=HiloGame,
    banner=BANNER,
    tagline="Kelly sizing speed run",
    make_widget=None,  # type: ignore[arg-type]  (cards are drawn by the bet screen)
    setup_rules=(),
    fair_rules=(),
    custom_fields=custom_fields,
    howto=howto,
    first_screen=first_screen,
    subtitle=SUBTITLE,
    custom_note=custom_note,
))
