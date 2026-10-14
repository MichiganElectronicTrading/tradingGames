"""The suite-wide Settings screen. Built from a list of sections (each game adds its own), each with typed options;
every change saves at once. ↑↓ setting · ←→ change value · R reset this section · Esc back."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games import settings
from met_games.widgets import AMBER, DIM, SELECTED, TITLE, KeyBar, TitledPanel, TopBar


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    choices: tuple[str, ...]  # stored values, in ←→ order
    default: str
    names: dict[str, str] = field(default_factory=dict)  # value → what the screen shows (default: VALUE)

    def name(self, value: str) -> str:
        return self.names.get(value, value.upper())


@dataclass(frozen=True)
class Section:
    game: str  # the settings.json namespace
    title: str
    options: tuple[Option, ...]
    note: str = ""
    # side panels for this section: (title, renderable) each
    panels: Callable[[], list[tuple[str, RenderableType]]] = lambda: []
    # the live preview from the section's current values and the preview's width
    preview: Callable[[dict[str, str], int], RenderableType] | None = None

    def values(self) -> dict[str, str]:
        """The saved values; anything missing or not a known choice reads as the default."""
        out = {}
        for o in self.options:
            v = settings.get(self.game, o.key, o.default)
            out[o.key] = v if v in o.choices else o.default
        return out


def all_sections() -> list[Section]:
    from met_games.app import SETTINGS_SECTIONS

    return list(SETTINGS_SECTIONS)


class SettingsScreen(Screen):
    BINDINGS = [
        Binding("up", "move(-1)", "setting", priority=True),
        Binding("down", "move(1)", "setting", priority=True),
        Binding("left", "change(-1)", "change", priority=True),
        Binding("right", "change(1)", "change", priority=True),
        Binding("r", "reset", "reset section"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    SettingsScreen #settings-body { height: 1fr; padding: 0 1; }
    SettingsScreen #settings-top { height: auto; }
    SettingsScreen #settings-list-panel { width: 3fr; }
    SettingsScreen #settings-side { width: 2fr; height: auto; }
    SettingsScreen #settings-preview { padding: 0 1; }
    """

    def __init__(self, sections: list[Section] | None = None) -> None:
        super().__init__()
        self.sections = sections if sections is not None else all_sections()
        self.rows = [(s, o) for s in self.sections for o in s.options]  # every selectable option, in order
        self.index = 0

    @property
    def section(self) -> Section:
        return self.rows[self.index][0]

    @property
    def option(self) -> Option:
        return self.rows[self.index][1]

    def compose(self) -> ComposeResult:
        yield TopBar("MET GAMES ▸ SETTINGS")
        with VerticalScroll(id="settings-body"):
            with Horizontal(id="settings-top"):
                yield TitledPanel("SETTINGS", Static(id="settings-list"), double=True, id="settings-list-panel")
                yield Vertical(id="settings-side")
            yield TitledPanel("PREVIEW", Static(id="settings-preview"), id="settings-preview-panel")
        yield KeyBar([("↑↓", "setting"), ("←→", "change value"), ("R", "reset this section"), ("Esc", "back")])

    def on_mount(self) -> None:
        self.refresh_side()
        self.refresh_view()
        self.call_after_refresh(self.refresh_view)

    def on_resize(self) -> None:
        self.refresh_view()

    # ── view ────────────────────────────────────────────────────────────────

    def list_text(self) -> Text:
        out = Text()
        for si, s in enumerate(self.sections):
            out.append(("\n\n" if si else "") + s.title, style=f"bold {TITLE}")
            values = s.values()
            for o in s.options:
                chosen = (s, o) == self.rows[self.index]
                out.append(f"\n  {o.label:<16}", style="bold" if chosen else "")
                out.append(f" ◂ {o.name(values[o.key]):^8} ▸ ", style=SELECTED if chosen else f"bold {AMBER}")
            if s.note:
                out.append(f"\n  {s.note}", style=DIM)
        return out

    def refresh_side(self) -> None:
        side = self.query_one("#settings-side", Vertical)
        side.remove_children()
        side.mount_all([TitledPanel(title, Static(body)) for title, body in self.section.panels()])

    def refresh_view(self) -> None:
        self.query_one("#settings-list", Static).update(self.list_text())
        preview = self.query_one("#settings-preview", Static)
        panel = self.query_one("#settings-preview-panel")
        if self.section.preview is None:
            panel.display = False
            return
        panel.display = True
        panel.border_title = f"PREVIEW · {self.section.title}"
        preview.update(self.section.preview(self.section.values(), preview.content_size.width))

    # ── keys ────────────────────────────────────────────────────────────────

    def action_move(self, delta: int) -> None:
        before = self.section
        self.index = max(0, min(len(self.rows) - 1, self.index + delta))
        if self.section is not before:
            self.refresh_side()
        self.refresh_view()

    def action_change(self, delta: int) -> None:
        s, o = self.rows[self.index]
        current = s.values()[o.key]
        i = o.choices.index(current)
        value = o.choices[max(0, min(len(o.choices) - 1, i + delta))]
        if value != current:
            settings.set(s.game, o.key, value)
        self.refresh_view()

    def action_reset(self) -> None:
        s = self.section
        for o in s.options:
            settings.set(s.game, o.key, o.default)
        self.refresh_view()
