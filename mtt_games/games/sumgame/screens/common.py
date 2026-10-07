"""Helpers shared by the sum-game screens."""

from __future__ import annotations

from rich.text import Text
from textual.app import App
from textual.screen import Screen
from textual.widget import Widget

from mtt_games.games.sumgame.config import SumConfig
from mtt_games.games.sumgame.engine import Round, SumSession
from mtt_games.games.sumgame.source import Source
from mtt_games.games.sumgame.stats import money, trade_label
from mtt_games.games.sumgame.ui import GameUI, ui_for
from mtt_games.widgets import DIM, GREEN, RED, TopBar


def crumb(session: SumSession) -> str:
    return f"{ui_for(session).crumb} ▸ {session.mode}"


def round_text(session: SumSession, rnd: Round) -> str:
    return f"ROUND {rnd.number}/{session.config.rounds}"


def top_bar(source: Source, crumb_text: str, round_txt: str = "", balance: object = None, id: str | None = None) -> TopBar:
    return TopBar(crumb_text, round_txt, balance, id=id, places=source.places)


def item_widget(ui: GameUI, rnd: Round, i: int, face_up: bool) -> Widget:
    item = rnd.items[i]
    return ui.make_widget(item, rnd.SOURCE.value(item, rnd.event), face_up, rnd.event)


def event_banner(source: Source, event: str) -> str:
    e = source.events[event]
    return f"⚡ MARKET EVENT · {e.name} — {e.rule}"


def log_text(session: SumSession) -> Text:
    """One line per finished round: trade, settle, P&L, report ✓/✗."""
    places = session.source.places
    out = Text()
    for rnd in session.rounds:
        if rnd.decision is None:
            continue
        if out:
            out.append("\n")
        out.append(f"R{rnd.number} ", style="bold")
        out.append(f"{trade_label(rnd):<13}", style=DIM if not rnd.decision.is_trade else "")
        out.append(f" →{rnd.settle:>4} ")
        pnl = rnd.pnl
        out.append(f"{money(pnl, places):>6}", style=GREEN if pnl > 0 else RED if pnl < 0 else DIM)
        if rnd.report_correct is not None:
            out.append(" ✓" if rnd.report_correct else " ✗", style=GREEN if rnd.report_correct else RED)
    return out


def new_session(app: App, config: SumConfig, mode: str) -> SumSession:
    seed_override = getattr(app, "seed_override", None)
    if config.seed is None and seed_override is not None:
        config = config.replace(seed=seed_override)
    return ui_for(config).session_cls(config, mode)


def next_round_screen(session: SumSession) -> Screen:
    """Deal the next round and return its screen, or the recap if the session can't continue."""
    from mtt_games.games.sumgame.screens.recap import RecapScreen
    from mtt_games.games.sumgame.screens.round import RoundScreen

    if not session.finished:
        session.new_round()
    return RecapScreen(session) if session.finished else RoundScreen(session)


def start_session(app: App, config: SumConfig, mode: str, *, switch: bool) -> None:
    """Open the first round of a new session (push from the lobby, switch from custom/recap)."""
    session = new_session(app, config, mode)
    screen = (ui_for(config).first_screen or next_round_screen)(session)
    if switch:
        app.switch_screen(screen)
    else:
        app.push_screen(screen)
