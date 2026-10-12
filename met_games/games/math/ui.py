"""Mental Math UI text: the banner, the lobby menu, each mode's rules, and the DIFFICULTY table."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from met_games.games.math.config import OPTIVER, SPRINT, SURVIVAL, ZETAMAC
from met_games.games.math.problems import BASE, CORE, DECFRAC, DESK, EASY, FAMILIES, FAMILY_LABELS, HARD, MEDIUM, PCT
from met_games.widgets import AMBER, DIM, TITLE

BANNER = """\
███    ███  █████  ████████ ██   ██
████  ████ ██   ██    ██    ██   ██
██ ████ ██ ███████    ██    ███████
██  ██  ██ ██   ██    ██    ██   ██
██      ██ ██   ██    ██    ██   ██"""

SUBTITLE = "mental math · exact answers · fast"

DAILY_ITEM, STATS_ITEM, QUIT_ITEM = "daily", "stats", "quit"
SOON = "soon"
# The MODES list: (kind, key, label). kind: "head" (section title), "mode", SOON (dim, not selectable), "item".
MENU: list[tuple[str, str, str]] = [
    ("head", "", "ARCADE"),
    ("mode", SPRINT, "SPRINT"),
    ("mode", SURVIVAL, "SURVIVAL"),
    (SOON, "chain", "CHAIN"),
    (SOON, "estimate", "ESTIMATE"),
    ("head", "", "TEST DRILLS"),
    ("mode", ZETAMAC, "ZETAMAC 120s"),
    ("mode", OPTIVER, "OPTIVER-STYLE 80/8"),
    (SOON, "flow", "FLOW-STYLE"),
    (SOON, "imc", "IMC/SIG-STYLE"),
    ("head", "", "MORE"),
    ("item", DAILY_ITEM, "DAILY CHALLENGE"),
    ("item", STATS_ITEM, "MY STATS"),
    ("item", QUIT_ITEM, "QUIT"),
]

RULES: dict[str, list[str]] = {
    SPRINT: [
        "2:00 — as many as you can (Custom: 0:30–5:00).",
        "Type the answer: it locks the moment it's exactly right — no Enter, no wrong. 13/16 or 0.8125 both count.",
        "Tab skips and resets the combo.",
        "Points = base × combo · combo ×(1 + 0.1 × streak), up to ×3.",
    ],
    SURVIVAL: [
        "Start with 0:30. Correct +10s EASY · +8s MEDIUM · +6s HARD; skip −5s.",
        "Every 5 correct the bonus drops 0.5s (never below +1s). Custom: your own starting bonus.",
        "It ends when the clock hits 0:00.",
        "Points = base × combo · combo ×(1 + 0.1 × streak), up to ×3.",
    ],
    ZETAMAC: [
        "The Zetamac default: (2–100) + (2–100), subtraction as reversed addition, (2–12) × (2–100), division as "
        "reversed multiplication.",
        "120 seconds. Answers lock when right; Tab skips.",
        "Raw score only — comparable with your Zetamac scores.",
    ],
    OPTIVER: [
        "Unofficial practice format: 80 questions in 8:00.",
        "Decimals & fractions, percentages and arithmetic at medium–hard; 4 options, one right.",
        "1–4 answers and moves on; S skips. No going back.",
        "+1 right, −1 wrong, 0 skip — your score is the NET.",
    ],
    SOON: ["Coming in v2."],
    DAILY_ITEM: [
        "The same 200 problems for everyone, seeded by the date in Detroit.",
        "Sprint 2:00 · MEDIUM · all four families. One attempt a day (honor system).",
        "Finish to get a score card you can paste anywhere.",
    ],
    STATS_ITEM: ["Bests per mode and difficulty, runs played, and your lifetime accuracy and median time per "
                 "problem type."],
    QUIT_ITEM: ["Leave MET Games."],
}

DIFFICULTY_ROWS: dict[str, tuple[str, str, str]] = {
    CORE: ("2-dig ± · 12×12 · ÷144", "3-dig ± · 2×2, 3×1 · ÷1-dig", "4-dig ± · 3×2 · ÷2-dig"),
    DECFRAC: ("½ ¼ ⅕ ↔ dec · 0.5×18", "8ths · 0.375×48 · a/b±c/d", "16ths · 0.0625×72 · 7/8−0.3125"),
    PCT: ("10/25/50% of", "any % of · % change", "chained · reverse"),
    DESK: ("$ P&L · 300×$3 · spread", "0.25×300 · notional · VWAP", "multi-fill · VWAP · marked"),
}
FAMILY_NAMES = {CORE: "core arithmetic", DECFRAC: "decimals & fractions", PCT: "percentages", DESK: "desk math"}


def difficulty_table(selected: str | None = None) -> Table:
    t = Table(show_edge=False, box=None, padding=(0, 1), pad_edge=False, expand=True, header_style=f"bold {TITLE}")
    t.add_column("", no_wrap=True)
    for lv in (EASY, MEDIUM, HARD):
        t.add_column(lv.upper(), ratio=1, no_wrap=True, overflow="ellipsis",
                     header_style=f"bold {AMBER}" if lv == selected else f"bold {TITLE}")
    for f in FAMILIES:
        t.add_row(Text(f"{FAMILY_LABELS[f]} {BASE[f]}", style="bold"),
                  *[Text(cell, style="" if lv == selected else DIM)
                    for lv, cell in zip((EASY, MEDIUM, HARD), DIFFICULTY_ROWS[f])])
    return t


def howto_lines(key: str) -> Text:
    out = Text()
    for i, line in enumerate(RULES.get(key, RULES[SOON])):
        out.append(("\n" if i else "") + "· ", style=AMBER)
        out.append(line)
    return out
