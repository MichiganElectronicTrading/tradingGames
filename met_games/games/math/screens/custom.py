"""Custom (Sprint/Survival with the CUSTOM difficulty): duration (Sprint) or the starting bonus (Survival), and
per family on/off, difficulty and weight."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.math.config import (
    BONUS_RANGE_MS,
    DURATION_RANGE,
    MODE_LABELS,
    SPRINT,
    SURVIVAL,
    MathConfig,
)
from met_games.games.math.problems import FAMILIES, LEVELS
from met_games.games.math.screens.common import clock_text, start_run
from met_games.games.math.ui import FAMILY_NAMES
from met_games.widgets import AMBER, DIM, SELECTED, KeyBar, TitledPanel, TopBar

DURATION_STEP = 15
BONUS_STEP_MS = 1_000


class MathCustomScreen(Screen):
    BINDINGS = [
        Binding("up", "move(-1)", show=False, priority=True),
        Binding("down", "move(1)", show=False, priority=True),
        Binding("left", "change(-1)", show=False, priority=True),
        Binding("right", "change(1)", show=False, priority=True),
        Binding("enter", "start", "start"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    MathCustomScreen #custom-body { padding: 1 2; height: 1fr; }
    MathCustomScreen #custom-panel { width: 80; }
    """

    def __init__(self, config: MathConfig) -> None:
        super().__init__()
        self.mode = config.mode
        self.duration = config.duration_s
        levels = config.level_map()
        weights = dict(config.weights)
        # per family: weight 0 = off, 1–5
        self.weight = {f: (weights.get(f, 1) if f in config.families else 0) for f in FAMILIES}
        self.level = dict(levels)
        self.bonus_ms, _ = config.survival_bonus()
        self.rows = (["duration"] if self.mode == SPRINT else ["bonus"] if self.mode == SURVIVAL else []) + \
            [(f, kind) for f in FAMILIES for kind in ("level", "weight")]
        self.index = 0

    def compose(self) -> ComposeResult:
        yield TopBar(f"MATH ▸ {MODE_LABELS[self.mode]} ▸ CUSTOM")
        with Vertical(id="custom-body"):
            yield TitledPanel("CUSTOM", Static(id="custom"), double=True, id="custom-panel")
        yield KeyBar([("↑↓", "move"), ("←→", "change"), ("⏎", "start"), ("Esc", "back")])

    def on_mount(self) -> None:
        self.refresh_view()

    def config(self) -> MathConfig:
        on = tuple(f for f in FAMILIES if self.weight[f])
        return MathConfig(mode=self.mode, difficulty="custom", duration_s=self.duration, families=on,
                          levels=tuple(self.level.items()), weights=tuple((f, self.weight[f]) for f in on),
                          bonus_ms=self.bonus_ms)

    def refresh_view(self) -> None:
        out = Text()
        for i, row in enumerate(self.rows):
            if row == "duration":
                label, value, hint = "duration", clock_text(self.duration * 1000), "0:30–5:00"
            elif row == "bonus":
                label, value, hint = "bonus per correct", f"+{self.bonus_ms / 1000:g}s", "1–20s · −0.5s every 5, floor 1s"
            else:
                f, kind = row
                if kind == "level":
                    label, value, hint = FAMILY_NAMES[f], self.level[f].upper(), "difficulty"
                else:
                    w = self.weight[f]
                    label, value, hint = "  weight", "off" if w == 0 else f"×{w}", "0 = off · drawn in proportion"
            line = Text(f" {label:<24}")
            line.append(f" ‹ {value:^8} › ", style=SELECTED if i == self.index else f"bold {AMBER}")
            line.append(f"  {hint}", style=DIM)
            out.append_text(line)
            out.append("\n")
        errors = self.config().errors()
        out.append("\n" + ("; ".join(errors) if errors else "⏎ to start"), style=DIM if not errors else "bold red")
        self.query_one("#custom", Static).update(out)

    def action_move(self, delta: int) -> None:
        self.index = max(0, min(len(self.rows) - 1, self.index + delta))
        self.refresh_view()

    def action_change(self, delta: int) -> None:
        row = self.rows[self.index]
        if row == "duration":
            lo, hi = DURATION_RANGE
            self.duration = max(lo, min(hi, self.duration + delta * DURATION_STEP))
        elif row == "bonus":
            lo, hi = BONUS_RANGE_MS
            self.bonus_ms = max(lo, min(hi, self.bonus_ms + delta * BONUS_STEP_MS))
        else:
            f, kind = row
            if kind == "level":
                self.level[f] = LEVELS[max(0, min(len(LEVELS) - 1, LEVELS.index(self.level[f]) + delta))]
            else:
                w = max(0, min(5, self.weight[f] + delta))
                if w == 0 and sum(1 for x in self.weight.values() if x) == 1:
                    self.app.bell()  # keep at least one family on
                    return
                self.weight[f] = w
        self.refresh_view()

    def action_start(self) -> None:
        cfg = self.config()
        if cfg.errors():
            self.app.bell()
            return
        start_run(self.app, cfg, switch=True)
