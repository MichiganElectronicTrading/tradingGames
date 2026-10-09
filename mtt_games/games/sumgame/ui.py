"""How a sum game looks: the per-game UI spec the shared screens read, plus a small registry so a
config (or session) can find its game's UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from textual.screen import Screen
from textual.widget import Widget

from mtt_games.games.sumgame.config import SumConfig
from mtt_games.games.sumgame.engine import SumSession
from mtt_games.games.sumgame.source import Source

# make_widget(item, value, face_up, event) -> a widget with `.tag`, the "fresh" CSS class, and
# show(face_up=, fresh=, tag=) — see CardWidget / DieWidget. `event` is for display choices only.
ItemWidgetFactory = Callable[[Any, int, bool, str | None], Widget]


@dataclass(frozen=True)
class GameUI:
    session_cls: type[SumSession]
    banner: str  # block-letter lobby banner
    tagline: str  # "market-taking drill"
    make_widget: ItemWidgetFactory
    setup_rules: tuple[str, ...]  # how-to-play: what gets dealt and how it settles
    fair_rules: tuple[str, ...]  # how-to-play: where fair value comes from
    # Optional hooks for a game that keeps the shared lobby/custom/how-to/stats screens but plays
    # differently. Each defaults to the sum-game behaviour when None.
    custom_fields: Callable[[], list[Any]] | None = None  # Custom screen rows (list of custom.Field)
    howto: Callable[[], list[tuple[str, list[str]]]] | None = None  # how-to-play (title, paragraphs)
    first_screen: Callable[[Any], Screen] | None = None  # a new session's first screen
    subtitle: str | None = None  # lobby line under the banner (default: "GAME · tagline")
    menu_extras: tuple[tuple[str, Callable[[GameUI], Screen]], ...] = ()  # lobby items after HOW TO PLAY
    lobby_note: str | None = None  # a line under the lobby panels

    @property
    def source(self) -> Source:
        return getattr(self.session_cls, "SOURCE", None) or self.session_cls.ROUND.SOURCE

    @property
    def crumb(self) -> str:
        return f"MTT GAMES ▸ {self.source.title}"

    @property
    def history_file(self) -> str:
        return f"{self.source.key}_history.jsonl"

    @property
    def presets_file(self) -> str:
        return f"{self.source.key}_presets.json"


_BY_CONFIG: dict[type[SumConfig], GameUI] = {}


def register(ui: GameUI) -> GameUI:
    _BY_CONFIG[ui.source.config_cls] = ui
    return ui


def ui_for(obj: SumConfig | SumSession) -> GameUI:
    config = obj.config if isinstance(obj, SumSession) else obj
    return _BY_CONFIG[type(config)]
