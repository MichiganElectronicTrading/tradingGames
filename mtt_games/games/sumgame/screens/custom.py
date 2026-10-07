"""Custom game: edit every config field, toggle events, load/save presets."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Static

from mtt_games import storage
from mtt_games.games.sumgame.config import EVENT_FREQS, SIZINGS, SumConfig, freq_label, noise_label
from mtt_games.games.sumgame.screens.common import start_session, top_bar
from mtt_games.games.sumgame.ui import GameUI
from mtt_games.widgets import AMBER, DIM, GREEN, RED, KeyBar, KeyButton, RowList, TitledPanel, TopBar, fmt_balance


def _clamp(lo: Any, hi: Any, inc: Any = 1) -> Callable[[Any, int], Any]:
    return lambda v, d: max(lo, min(hi, v + d * inc))


def _cycle(options: tuple) -> Callable[[Any, int], Any]:
    def step(v: Any, d: int) -> Any:
        i = next((i for i, o in enumerate(options) if o == v or (isinstance(o, float) and math.isclose(o, v))), 0)
        return options[max(0, min(len(options) - 1, i + d))]

    return step


def _seed_step(v: int | None, d: int) -> int | None:
    if v is None:
        return 1 if d > 0 else None
    return None if v + d < 1 else v + d


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    hint: str
    step: Callable[[Any, int], Any]
    show: Callable[[Any], str] = str


def _on_off(v: bool) -> str:
    return "on" if v else "off"


def fields_for(cfg_cls: type[SumConfig]) -> list[Field]:
    """Editable rows. Price fields step in the game's tick (quote noise: half a point, or one tick
    if that is finer)."""
    noun, tick, price = cfg_cls.NOUN, cfg_cls.TICK, cfg_cls.price
    n_min, n_max = cfg_cls.COUNT_FIELDS
    noise_step = min(0.5, float(tick))
    return [
        Field(n_min, f"{noun} min", "2–10 dealt per round", _clamp(2, 10)),
        Field(n_max, f"{noun} max", "random in [min, max]", _clamp(2, 10)),
        Field("face_up_min", "face up min", "≥ 0", _clamp(0, 10)),
        Field("face_up_max", "face up max", f"≤ {noun} min", _clamp(0, 10)),
        Field("rounds", "rounds", "1–20", _clamp(1, 20)),
        Field("timer_s", "timer", "5–120 s", _clamp(5, 120, 5), lambda v: f"{v}s"),
        Field("budget", "budget", "starting balance", _clamp(100, 10_000, 100), fmt_balance),
        Field(
            "spread", "spread", f"ask − bid, {price(tick)}–{price(cfg_cls.SPREAD_MAX)}",
            _clamp(tick, cfg_cls.SPREAD_MAX, tick), price,
        ),
        Field(
            "quote_noise_sd", "quote noise sd", "mid = fair + N(0, sd)", _clamp(0.0, 6.0, noise_step),
            lambda v: noise_label(cfg_cls, v),
        ),
        Field("sizing", "sizing", "fixed 1 or choose", _cycle(SIZINGS), lambda v: "fixed 1" if v == "fixed" else v),
        Field("mid_round_flip", "mid-round flip", "a hidden one turns up", lambda v, d: d > 0, _on_off),
        Field("stale_quotes", "stale quotes", "quote may not update", lambda v, d: d > 0, _on_off),
        Field("event_freq", "event freq", "chance of an event", _cycle(EVENT_FREQS), freq_label),
        Field("seed", "seed", "random = new each time", _seed_step, lambda v: "random" if v is None else str(v)),
    ]


class PresetNameScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "cancel")]

    DEFAULT_CSS = """
    PresetNameScreen > TitledPanel { width: 44; background: #0B0F14; }
    """

    def compose(self) -> ComposeResult:
        yield TitledPanel(
            "SAVE PRESET", Input(placeholder="preset name", classes="wide"), Static("⏎ save · esc cancel", classes="dim"),
            double=True,
        )

    def on_input_submitted(self, message: Input.Submitted) -> None:
        self.dismiss(message.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class CustomScreen(Screen):
    BINDINGS = [
        Binding("left", "change(-1)", show=False),
        Binding("right", "change(1)", show=False),
        Binding("space", "toggle_event", show=False),
        Binding("s", "save", "save preset"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    CustomScreen #custom-body { height: 1fr; padding: 0 1; }
    CustomScreen #settings { width: 1fr; }
    CustomScreen #validity { margin-top: 1; }
    CustomScreen #custom-right { width: 46; }
    """

    def __init__(self, ui: GameUI, base: SumConfig | None = None) -> None:
        super().__init__()
        self.ui = ui
        self.src = ui.source
        self.presets = self.src.presets
        self.fields = ui.custom_fields() if ui.custom_fields else fields_for(self.src.config_cls)
        self.event_keys = tuple(self.src.events)
        self.config = base or self.presets["EASY"]
        self.saved = self.load_saved_presets()

    def load_saved_presets(self) -> dict[str, SumConfig]:
        out = {}
        for name, data in storage.read_json(self.ui.presets_file, {}).items():
            try:
                out[name] = self.src.config_cls.from_dict(data)
            except (TypeError, ValueError, ArithmeticError):
                continue
        return out

    def compose(self) -> ComposeResult:
        yield top_bar(self.src, f"{self.ui.crumb} ▸ CUSTOM", "", self.config.budget)
        with Horizontal(id="custom-body"):
            with TitledPanel("SETTINGS", double=True, id="settings"):
                yield RowList(self.settings_rows(), id="settings-list")
                yield Static(id="validity")
            with Vertical(id="custom-right"):
                yield TitledPanel("MARKET EVENTS", RowList(self.event_rows(), id="events-list"))
                yield TitledPanel("PRESETS", RowList(self.preset_rows(), id="presets-list"))
                yield KeyButton("▶ START", id="start", classes="start")
        yield KeyBar([
            ("↑↓", "move"), ("←→", "change"), ("Tab", "next panel"), ("Space", "toggle event"),
            ("⏎", "start / load"), ("S", "save preset"), ("Esc", "back"),
        ])

    def on_mount(self) -> None:
        self.query_one("#settings-list").focus()
        self.refresh_all()

    # ── rows ────────────────────────────────────────────────────────────────

    def settings_rows(self) -> list[Text]:
        rows = []
        for f in self.fields:
            row = Text(f"{f.label:<15}│ ")
            row.append(f"◂ {f.show(getattr(self.config, f.key)):^9} ▸", style="bold")
            row.append(" │ ")
            row.append(f.hint, style=DIM)
            rows.append(row)
        return rows

    def event_rows(self) -> list[Text]:
        rows = []
        for key in self.event_keys:
            on = key in self.config.enabled_events
            row = Text("[x] " if on else "[ ] ", style=f"bold {GREEN}" if on else DIM)
            row.append(f"{self.src.events[key].name:<15}", style="bold" if on else DIM)
            row.append(key, style=DIM)
            rows.append(row)
        return rows

    def preset_rows(self) -> list[str]:
        return [f"load {name}" for name in self.presets] + [f"load {name}  (saved)" for name in self.saved]

    def refresh_all(self) -> None:
        self.query_one("#settings-list", RowList).set_rows(self.settings_rows())
        self.query_one("#events-list", RowList).set_rows(self.event_rows())
        self.query_one("#presets-list", RowList).set_rows(self.preset_rows())
        self.query_one(TopBar).set(balance=self.config.budget)
        lo, hi = self.src.settle_range(self.config)
        line = Text(f"settles between {lo} and {hi}   ", style=AMBER)
        errs = self.config.errors()
        if errs:
            line.append(f"✗ {errs[0]}", style=f"bold {RED}")
        else:
            line.append("settings valid ✓", style=f"bold {GREEN}")
        self.query_one("#validity", Static).update(line)

    # ── actions ─────────────────────────────────────────────────────────────

    def action_change(self, delta: int) -> None:
        settings = self.query_one("#settings-list", RowList)
        if not settings.has_focus:
            return
        f = self.fields[settings.index]
        self.config = self.config.replace(**{f.key: f.step(getattr(self.config, f.key), delta)})
        self.refresh_all()

    def action_toggle_event(self) -> None:
        events = self.query_one("#events-list", RowList)
        if not events.has_focus:
            return
        key = self.event_keys[events.index]
        enabled = set(self.config.enabled_events) ^ {key}
        self.config = self.config.replace(enabled_events=tuple(k for k in self.event_keys if k in enabled))
        self.refresh_all()

    def on_row_list_chosen(self, message: RowList.Chosen) -> None:
        list_id = message.row_list.id
        if list_id == "settings-list":
            self.start()
        elif list_id == "events-list":
            self.action_toggle_event()
        elif list_id == "presets-list":
            names = list(self.presets) + list(self.saved)
            name = names[message.index]
            self.config = self.presets.get(name) or self.saved[name]
            self.refresh_all()
            self.notify(f"loaded {name}")

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        self.start()

    def start(self) -> None:
        errs = self.config.errors()
        if errs:
            self.notify(f"can't start: {errs[0]}", severity="error")
            return
        start_session(self.app, self.config, "CUSTOM", switch=True)

    def action_save(self) -> None:
        if self.config.errors():
            self.notify("fix the settings before saving", severity="error")
            return
        self.app.push_screen(PresetNameScreen(), self._save_as)

    def _save_as(self, name: str | None) -> None:
        if not name:
            return
        if name.upper() in self.presets:
            self.notify(f"{name} is a built-in preset name", severity="error")
            return
        data = storage.read_json(self.ui.presets_file, {})
        data[name] = self.config.to_dict()
        storage.write_json(self.ui.presets_file, data)
        self.saved = self.load_saved_presets()
        self.refresh_all()
        self.notify(f"saved preset {name}")
