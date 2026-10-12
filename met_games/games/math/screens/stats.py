"""MY STATS: bests and runs played per mode × difficulty, and lifetime accuracy and median time per problem type."""

from __future__ import annotations

from collections import Counter

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math.config import DAILY, DRILL, MODE_LABELS, MODES
from met_games.games.math.history import best_key, lifetime, load_bests, load_history, load_runs
from met_games.games.math.problems import SUBTYPE_FAMILY, SUBTYPE_LABELS, FAMILY_LABELS
from met_games.games.math.screens.common import secs
from met_games.widgets import DIM, TITLE, KeyBar, TitledPanel, TopBar


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True)
    return t


def bests_table() -> Table | Text:
    bests = load_bests()
    played = Counter((r.get("mode"), r.get("difficulty")) for r in load_runs())
    keys = sorted({k for k in played} | {tuple(k.split("/", 1)) for k in bests},
                  key=lambda k: ((MODES + (DRILL, DAILY)).index(k[0]) if k[0] in MODES + (DRILL, DAILY) else 99,
                                 str(k[1])))
    if not keys:
        return Text("no runs yet", style=DIM)
    t = _table("MODE", "DIFFICULTY", "RUNS", "BEST", right=("RUNS",))
    for mode, diff in keys:
        b = bests.get(best_key(mode, diff), {})
        parts = [f"{b[f]:,} {name}" for f, name in (("correct", "✓"), ("points", "pts"), ("raw", "raw"),
                                                     ("net", "net")) if f in b]
        t.add_row(MODE_LABELS.get(mode, mode), str(diff), str(played.get((mode, diff), 0)),
                  " · ".join(parts) or "—")
    return t


def lifetime_table() -> Table | Text:
    rows = lifetime(load_history())
    if not rows:
        return Text("no problems logged yet", style=DIM)
    t = _table("FAMILY", "TYPE", "SEEN", "ACCURACY", "MEDIAN", right=("SEEN", "ACCURACY", "MEDIAN"))
    for sub, seen, right, med in rows:
        t.add_row(FAMILY_LABELS[SUBTYPE_FAMILY[sub]], SUBTYPE_LABELS[sub], str(seen), f"{100 * right // seen}%",
                  secs(med))
    return t


class StatsScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "back"), Binding("l", "app.pop_screen", "lobby", show=False)]

    DEFAULT_CSS = """
    StatsScreen #stats-body { height: 1fr; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield TopBar("MATH ▸ MY STATS")
        with VerticalScroll(id="stats-body"):
            yield TitledPanel("BESTS · RUNS PLAYED", Static(bests_table(), id="bests"), double=True)
            yield TitledPanel("BY PROBLEM TYPE · LIFETIME", Static(lifetime_table(), id="lifetime"))
        yield KeyBar([("↑↓", "scroll"), ("Esc", "back")])
