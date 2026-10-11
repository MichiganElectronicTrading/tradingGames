"""Helpers shared by the Trading Game screens: bars, the table panel, timer, standings, and flow."""

from __future__ import annotations

import math

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Static

from met_games.games.sumgame.engine import BUY, SELL, TIMEOUT
from met_games.games.sumgame.screens.common import event_banner
from met_games.games.sumgame.stats import money
from met_games.games.sumgame.ui import ui_for
from met_games.games.trade.engine import TRADERS, TURNS, YOU, Action, Hand, TradeSession, Turn
from met_games.games.trade.stats import standings
from met_games.widgets import AMBER, DIM, GREEN, RED, SELECTED, TITLE, TitledPanel, TopBar, big_lines

CIRCLED = "①②③④"
CURRENT_ROW = f"bold {AMBER} on #2A3340"
BAR_WIDTH = 26


class TradeScreen(Screen):
    """Base for the hand screens: shared layout rules."""

    DEFAULT_CSS = """
    TradeScreen #body { height: 1fr; }
    TradeScreen #left { width: 1fr; }
    TradeScreen .cards { height: auto; margin-top: 1; }
    TradeScreen .flip-line { height: auto; }
    """


def crumb(session: TradeSession) -> str:
    return f"{session.source.title} ▸ {session.mode}"


def top_bar(session: TradeSession, balance: int) -> TopBar:
    hand = session.current
    return TopBar(crumb(session), f"HAND {hand.number} / {session.config.hands}", balance)


def seat_name(hand: Hand, i: int) -> str:
    who = hand.seats[i]
    return f"{CIRCLED[i]} {'YOU MAKE' if who == YOU else who}"


def turn_bar_text(hand: Hand, settle: bool = False) -> Text:
    """`① YOU MAKE ▸ ② DELTA ▸ ③ GAMMA ▸ ④ THETA ▸ SETTLE` in seat order: the open turn in reverse
    amber, finished turns green with ✓, the rest dim."""
    out = Text(" ")
    for i in range(TURNS):
        label = seat_name(hand, i)
        if i < len(hand.turns) and hand.turns[i].done:
            out.append(f"{label} ✓", style=f"bold {GREEN}")
        elif i == len(hand.turns) - 1 and not settle:
            out.append(f" {label} ", style=SELECTED)
        else:
            out.append(label, style=DIM)
        out.append(" ▸ ", style=DIM)
    out.append(" SETTLE " if settle else "SETTLE", style=SELECTED if settle else DIM)
    return out


class TurnBar(Static):
    DEFAULT_CSS = """
    TurnBar { height: 1; background: #1C232C; }
    """

    def __init__(self, hand: Hand, settle: bool = False) -> None:
        super().__init__(turn_bar_text(hand, settle))
        self.hand, self.settle = hand, settle

    def refresh_bar(self) -> None:
        self.update(turn_bar_text(self.hand, self.settle))


def header(session: TradeSession, balance: int, settle: bool = False) -> ComposeResult:
    """Top bar, turn bar and (on an event hand) the event banner."""
    hand = session.current
    yield top_bar(session, balance)
    yield TurnBar(hand, settle)
    if hand.event:
        yield Static(event_banner(session.source, hand.event), classes="event-banner")


def table_info(hand: Hand) -> str:
    m = hand.public()
    up_sum = sum(hand.values[i] for i in hand.face_up)
    return f"face up {up_sum} · hidden {len(hand.hidden)} · settles {m.settle_min}–{m.settle_max}"


def flip_text(hand: Hand, turn: Turn) -> Text:
    if turn.flipped is None:
        return Text()
    return Text(f"▲ {hand.items[turn.flipped]} turned face up", style=f"bold {AMBER}")


def table_panel(session: TradeSession, title: str = "TABLE") -> TitledPanel:
    """The cards (a card flipped just before this turn is tagged NEW), the info line and any flip line."""
    hand = session.current
    ui = ui_for(session.config)
    turn = hand.turn
    widgets = []
    for i, card in enumerate(hand.items):
        w = ui.make_widget(card, hand.SOURCE.value(card, hand.event), i in hand.face_up, hand.event)
        if i == turn.flipped:
            w.set_class(True, "fresh")
            w.tag = "NEW"
        widgets.append(w)
    return TitledPanel(
        title, Horizontal(*widgets, classes="cards"), Static(table_info(hand), classes="dim"),
        Static(flip_text(hand, turn), classes="flip-line"), id="table",
    )


def clock_text(remaining: float, total: float) -> Text:
    secs = math.ceil(max(0.0, remaining))
    color = RED if remaining < 5 else AMBER
    out = Text()
    for line in big_lines(f"{secs // 60:02d}:{secs % 60:02d}"):
        out.append(line + "\n", style=f"bold {color}")
    filled = round(BAR_WIDTH * max(0.0, remaining) / total)
    out.append("█" * filled, style=color)
    out.append("░" * (BAR_WIDTH - filled), style=DIM)
    return out


def big_number(text: str, style: str, width: int = 0) -> Text:
    out = Text()
    for i, line in enumerate(big_lines(text)):
        out.append(("\n" if i else "") + line.center(width), style=style)
    return out


def standings_table(session: TradeSession) -> Table:
    t = Table(box=None, show_header=False, pad_edge=False, expand=True)
    t.add_column(no_wrap=True)
    t.add_column(no_wrap=True)
    t.add_column(justify="right", no_wrap=True)
    for rank, who, total in standings(session):
        t.add_row(f"{rank}.", Text(who, style=f"bold {AMBER}" if who == YOU else ""),
                  Text(money(total), style=GREEN if total > 0 else RED if total < 0 else DIM))
    return t


def traders_text(hand: Hand, peeks_mode: str) -> Text:
    out = Text()
    for who in TRADERS:
        out.append(f"{who:<6}", style="bold")
        out.append(f" seat {CIRCLED[hand.seat_of(who)]}\n", style=DIM)
    if not hand.hidden:
        out.append("no hidden cards — nobody peeked", style=DIM)
    elif peeks_mode == "one":
        out.append("one of them has peeked at one hidden card", style=DIM)
    else:
        out.append("each has peeked at one hidden card", style=DIM)
    out.append("\nyour seat this hand: ", style=DIM)
    out.append(CIRCLED[hand.seat_of(YOU)], style=f"bold {AMBER}")
    return out


def did(a: Action) -> str:
    """'bought 5' / 'sold 2' / 'passed' / 'timed out'."""
    if a.action == BUY:
        return f"bought {a.size}"
    if a.action == SELL:
        return f"sold {a.size}"
    return "timed out" if a.action == TIMEOUT else "passed"


def markets_table(hand: Hand) -> Table:
    """MARKETS SO FAR: one row per turn this hand (maker, quote, who did what); current turn highlighted."""
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for col in ("TURN", "MAKER", "QUOTE", "WHO DID WHAT"):
        t.add_column(col, no_wrap=col != "WHO DID WHAT")
    for i, turn in enumerate(hand.turns):
        if not turn.posted:
            quote, what = "—", "no market (quote timer ran out)"
        else:
            quote = f"{turn.bid} @ {turn.ask} ×{turn.size}"
            what = " · ".join(f"{a.who} {did(a)}" for a in turn.actions) or "you act first …"
        current = i == len(hand.turns) - 1
        t.add_row(CIRCLED[i], turn.maker, quote, what, style=CURRENT_ROW if current else None)
    return t


def position_text(session: TradeSession) -> Text:
    hand = session.current
    pos, cash = hand.position[YOU], hand.cash[YOU]
    m = hand.public()
    out = Text("position ", style=DIM)
    out.append(f"{pos:+d}", style=f"bold {GREEN if pos > 0 else RED if pos < 0 else ''}")
    out.append("   cash ", style=DIM)
    out.append(money(cash), style="bold")
    worst = session.worst_after(0, 0)
    out.append(f"\nworst case at {m.settle_min}–{m.settle_max}: ", style=DIM)
    out.append(f"−${worst}" if worst else "no loss", style=RED if worst else GREEN)
    out.append(f"\nlimit (balance) ${session.balance}", style=DIM)
    return out


# ── flow ─────────────────────────────────────────────────────────────────────


def turn_screen(session: TradeSession) -> Screen:
    from met_games.games.trade.screens.turns import MakeScreen, TakeScreen

    return MakeScreen(session) if session.current.turn.maker == YOU else TakeScreen(session)


def next_screen(session: TradeSession) -> Screen:
    """Deal the next hand and return its first turn's screen, or the recap when the session is over."""
    from met_games.games.trade.screens.recap import RecapScreen

    if session.finished:
        return RecapScreen(session)
    session.new_hand()
    return turn_screen(session)


def advance(app: App, session: TradeSession) -> None:
    """After a finished turn: open the next turn's screen, or the settle screen after turn 4."""
    from met_games.games.trade.screens.settle import SettleScreen

    turn = session.next_turn()
    app.switch_screen(SettleScreen(session) if turn is None else turn_screen(session))


def next_label(hand: Hand) -> str:
    n = len(hand.turns)
    if n >= TURNS:
        return "SETTLE — the cards flip"
    who = hand.seats[n]
    return f"{CIRCLED[n]} {'YOU make' if who == YOU else who + ' makes'} a market"

