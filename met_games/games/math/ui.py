"""Mental Math UI text: the banner, the lobby menu, each mode's rules, and the DIFFICULTY table."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from met_games.games.math.config import CHAIN, ESTIMATE, FLOW, OPTIVER, PROB_DRILL, SPRINT, SURVIVAL, ZETAMAC
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
    ("mode", CHAIN, "CHAIN"),
    ("mode", ESTIMATE, "ESTIMATE"),
    ("head", "", "TEST DRILLS"),
    ("mode", ZETAMAC, "ZETAMAC 120s"),
    ("mode", OPTIVER, "OPTIVER-STYLE 80/8"),
    ("mode", FLOW, "FLOW-STYLE 60/6"),
    ("mode", PROB_DRILL, "PROBABILITY DRILL"),
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
    CHAIN: [
        "One running number: each link applies one operation to the carry, and your answer is the new carry.",
        "Type it and press Enter. A wrong answer or the step clock (15s EASY · 12s MEDIUM · 10s HARD) ends the chain.",
        "EASY ± × ÷ to 3 digits · MEDIUM adds ×/÷ to 12 and ±10/20/25/50% · HARD ×/÷ to 19, any %, hidden carry.",
        "Link points = 100 (150 for %) × combo · combo ×(1 + 0.1 × links so far), up to ×3.",
    ],
    ESTIMATE: [
        "15 questions, 15s each: big ×, ÷ by a decimal, % of, √ of a non-square, × 0.0xxx.",
        "Type a number (commas are ignored) and press Enter; a timeout scores 0.",
        "Within 1% → 100 · 5% → 50 · 10% → 25, else 0 · ×2 within 4s, ×1.5 within 8s.",
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
    FLOW: [
        "Unofficial practice format: 60 questions in 6:00 — arithmetic, decimals and fractions at medium–hard.",
        "Type the answer and press Enter; an empty Enter skips. Wrong answers still move on; no going back.",
        "No right or wrong until the end. Your score is the number correct.",
        "Esc hides the board but the clock keeps running — it's a test.",
    ],
    PROB_DRILL: [
        "20 probability questions in 10:00: dice, coins, expected value, counting card hands (HARD adds "
        "conditional).",
        "Card questions want a whole number of ways (2,598,960 is fine); the rest a fraction or a decimal to 3+ "
        "places within 0.0005. Enter; S skips.",
        "After each answer: ✓, or ✗ with the right answer — and WHY, naming the mistake when it's a known one.",
        "ADAPTIVE plays your own probability level (1–10).",
    ],
    SOON: ["Coming soon."],
    DAILY_ITEM: [
        "The same 200 problems for everyone, seeded by the date in Detroit.",
        "Sprint 2:00 · MEDIUM · all four families. One attempt a day (honor system).",
        "Finish to get a score card you can paste anywhere.",
    ],
    STATS_ITEM: ["Your last 20 runs per mode, median time per family (first 10 vs last 10 runs), your adaptive "
                 "levels with 7-day arrows, bests, and what to focus on next (F drills it)."],
    QUIT_ITEM: ["Leave MET Games."],
}

ADAPTIVE_RULES = [
    "ADAPTIVE: a level 1–10 per skill track. 3 fast right answers in a row → up; a miss, a skip or 2 slow answers "
    "→ down.",
]

CHAIN_ROWS = (("carry", "≤ 3 digits", "≤ 4 digits", "≤ 4 digits"), ("step clock", "15s", "12s", "10s"),
              ("ops", "± 1–2 dig · ×÷ 2–9", "×÷ to 12 · ±10/20/25/50%", "×÷ to 19 · any % · hidden"))
PROB_ROWS = (("dice", "one die", "two dice · sums · max", "at least one in n · all"),
             ("cards (count)", "2-card hands", "3 cards · 5-card basics", "5-card hands"),
             ("coins & EV", "≤ 3 coins · coin bets", "≤ 4 coins · die EV", "≤ 6 coins · runs · EV games"),
             ("conditional", "—", "—", "given at least one …"))
ESTIMATE_ROWS = (("operands", "3-dig × 2-dig", "4-digit, 1 dp", "4–5 digit, 2–3 dp"),
                 ("√", "3-digit", "4-digit", "5-digit"), ("scoring", "1% 100 · 5% 50", "10% 25 · else 0",
                                                          "×2 ≤4s · ×1.5 ≤8s"))

DIFFICULTY_ROWS: dict[str, tuple[str, str, str]] = {
    CORE: ("2-dig ± · 12×12 · ÷144", "3-dig ± · 2×2, 3×1 · ÷1-dig", "4-dig ± · 3×2 · ÷2-dig"),
    DECFRAC: ("½ ¼ ⅕ ↔ dec · 0.5×18", "8ths · 0.375×48 · a/b±c/d", "16ths · 0.0625×72 · 7/8−0.3125"),
    PCT: ("10/25/50% of", "any % of · % change", "chained · reverse"),
    DESK: ("$ P&L · 300×$3 · spread", "0.25×300 · notional · VWAP", "multi-fill · VWAP · marked"),
}
FAMILY_NAMES = {CORE: "core arithmetic", DECFRAC: "decimals & fractions", PCT: "percentages", DESK: "desk math"}


def difficulty_table(selected: str | None = None, mode: str | None = None) -> Table:
    t = Table(show_edge=False, box=None, padding=(0, 1), pad_edge=False, expand=True, header_style=f"bold {TITLE}")
    t.add_column("", no_wrap=True)
    for lv in (EASY, MEDIUM, HARD):
        t.add_column(lv.upper(), ratio=1, no_wrap=True, overflow="ellipsis",
                     header_style=f"bold {AMBER}" if lv == selected else f"bold {TITLE}")
    if mode in (CHAIN, ESTIMATE, PROB_DRILL):
        table = {CHAIN: CHAIN_ROWS, ESTIMATE: ESTIMATE_ROWS, PROB_DRILL: PROB_ROWS}[mode]
        rows = [(Text(label, style="bold"), *cells) for label, *cells in table]
    else:
        families = (CORE, DECFRAC) if mode == FLOW else FAMILIES  # Flow-style: core and decfrac at medium–hard
        rows = [(Text(f"{FAMILY_LABELS[f]} {BASE[f]}", style="bold"), *DIFFICULTY_ROWS[f]) for f in families]
    for label, *cells in rows:
        t.add_row(label, *[Text(cell, style="" if lv == selected else DIM) for lv, cell in zip((EASY, MEDIUM, HARD),
                                                                                               cells)])
    return t


def howto_lines(key: str, adaptive: bool = False) -> Text:
    out = Text()
    lines = RULES.get(key, RULES[SOON]) + (ADAPTIVE_RULES if adaptive else [])
    for i, line in enumerate(lines):
        out.append(("\n" if i else "") + "· ", style=AMBER)
        out.append(line)
    return out
