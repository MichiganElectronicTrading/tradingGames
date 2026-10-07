"""How to play: one scrolling panel of rules (game-specific setup + fair value, shared everything else)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from mtt_games.games.sumgame.ui import GameUI
from mtt_games.widgets import AMBER, KeyBar, TopBar


def sections(ui: GameUI) -> list[tuple[str, list[str]]]:
    if ui.howto is not None:
        return ui.howto()
    src = ui.source
    whole = src.places == 0
    quote = "two-way integer quote" if whole else f"two-way quote in {src.price(src.tick)} ticks"
    reporting = (
        "Exact answers count as correct." if whole
        else "Answers are checked to the cent (17.5 and 17.50 are the same answer)."
    )
    return [
        ("THE SETUP", list(ui.setup_rules)),
        ("THE MARKET", [
            f"A market maker shows a {quote}: BID @ ASK.",
            "Buy at the ask if you think the settlement will be higher; sell at the bid if lower; or pass. "
            "One trade per round.",
            "Long P&L = (settle − ask) × size.   Short P&L = (bid − settle) × size.",
            "The timer runs down. At 0 you auto-pass and the round is logged as timed out.",
        ]),
        ("FAIR VALUE", [
            *ui.fair_rules,
            "Edge per unit: buying = fair − ask, selling = bid − fair. Positive edge is a good trade even when "
            "the draw goes against you. The game never shows fair before the reveal — that's your job.",
        ]),
        ("RISK", [
            "You may only open a position whose worst-case loss fits in your balance: "
            "max long = ⌊balance ÷ (ask − lowest settle)⌋, max short = ⌊balance ÷ (highest settle − bid)⌋, "
            "both capped at 100. A side that can't lose is capped at 100; a side whose max is below 1 is disabled.",
            "If your balance hits 0, or a new round opens with neither side tradable, the session ends early.",
        ]),
        ("REPORTING", [
            f"After each reveal you must type your round P&L. {reporting} "
            "Reporting never changes your balance — it's a mental-math stat.",
        ]),
        ("MARKET EVENTS", [f"{e.name}: {e.rule}." for e in src.events.values()]),
        ("HARD MODE", [
            f"Mid-round flip: partway through the timer a hidden {src.item} turns face up (tagged NEW). "
            "The quote may or may not update — watch the tape and decide whether the market is stale.",
        ]),
        ("CONTROLS", [
            "Lobby: ↑↓ move · ⏎ start · C custom · H how to play · Q quit.",
            "Round: B buy · S sell · P pass · ←→ size ±1 · shift+←→ ±5 (choose-size modes).",
            "Reveal: type P&L + ⏎ · W explain fair value · ⏎ next round.",
            "Recap: R replay same seed · N next difficulty · E export CSV · L lobby · Q quit.",
        ]),
    ]


def rules_text(ui: GameUI) -> Text:
    out = Text()
    for i, (title, paras) in enumerate(sections(ui)):
        if i:
            out.append("\n\n")
        out.append(title, style=f"bold {AMBER}")
        for p in paras:
            out.append("\n" + p)
    return out


class HowToScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "back"), Binding("q", "app.pop_screen", "back", show=False)]

    DEFAULT_CSS = """
    HowToScreen #howto-scroll { height: 1fr; margin: 0 1; border: double #3FA7B5; border-title-color: #5FD4E0;
                                border-title-style: bold; padding: 0 1; }
    """

    def __init__(self, ui: GameUI) -> None:
        super().__init__()
        self.ui = ui

    def compose(self) -> ComposeResult:
        yield TopBar(f"{self.ui.crumb} ▸ HOW TO PLAY")
        scroll = VerticalScroll(Static(rules_text(self.ui)), id="howto-scroll")
        scroll.border_title = "HOW TO PLAY"
        yield scroll
        yield KeyBar([("↑↓", "scroll"), ("Esc", "back")])

    def on_mount(self) -> None:
        self.query_one("#howto-scroll").focus()
