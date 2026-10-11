"""Settle screen: every card up with the sum, who peeked at what, the hand leaderboard, your P&L
report, your trades, and the W walkthrough."""

from __future__ import annotations

from time import monotonic

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static

from met_games.games.sumgame.engine import BUY, TIMEOUT
from met_games.games.sumgame.screens.reveal import settle_line
from met_games.games.sumgame.stats import money
from met_games.games.sumgame.ui import ui_for
from met_games.games.trade.engine import PLAYERS, TRADERS, YOU, Hand, TradeSession, Turn
from met_games.games.trade.screens.common import CIRCLED, TradeScreen, header, next_screen
from met_games.games.trade.stats import market_label
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar


def _pnl_text(x: int) -> Text:
    return Text(money(x), style=f"bold {GREEN if x > 0 else RED if x < 0 else ''}")


def peeks_line(hand: Hand) -> Text:
    out = Text("who peeked: ", style=DIM)
    for i, t in enumerate(TRADERS):
        if i:
            out.append(" · ", style=DIM)
        card = hand.peeks[t]
        out.append(f"{t} ", style="bold")
        out.append(f"saw {hand.items[card]}" if card is not None else "saw nothing", style=AMBER if card is not None
                   else DIM)
    return out


def leaderboard(hand: Hand) -> Table:
    """Rank, player, hand P&L (yours `??` until reported), position, the market each player made."""
    reported = hand.reported is not None
    ranks, pnls = hand.ranks(), hand.pnls()
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for col in ("RANK", "PLAYER", "HAND P&L", "POSITION", "MARKET MADE"):
        t.add_column(col, justify="right" if col in ("HAND P&L", "POSITION") else "left", no_wrap=True)
    for who in sorted(PLAYERS, key=lambda p: (ranks[p], PLAYERS.index(p))):
        hide = who == YOU and not reported
        t.add_row(
            "?" if hide else str(ranks[who]),
            Text(who, style=f"bold {AMBER}" if who == YOU else "bold"),
            Text("??", style=f"bold {AMBER}") if hide else _pnl_text(pnls[who]),
            f"{hand.position[who]:+d}",
            market_label(hand.turns[hand.seat_of(who)]),
        )
    return t


def trade_row(hand: Hand, turn: Turn) -> tuple[str, int, str]:
    """(what you did, $, short reason) for one turn."""
    s = hand.settle
    if turn.maker == YOU:
        if not turn.posted:
            return "made no market (timer)", 0, "timed out"
        bf, af = turn.bid_filled, turn.ask_filled
        pnl = sum(hand.fill_pnl(turn, a) for a in turn.fills)
        what = f"made {turn.bid} @ {turn.ask}: bought {bf}, sold {af}"
        if not bf and not af:
            return what, 0, "nobody traded"
        trips, net = min(bf, af), bf - af
        parts = [f"locked {trips}×{turn.width}=${trips * turn.width}"] if trips else []
        if net:
            price = turn.bid if net > 0 else turn.ask
            parts.append(f"{'long' if net > 0 else 'short'} {abs(net)} @ {price} vs settle {s}")
        return what, pnl, " · ".join(parts)
    a = turn.action_of(YOU)
    if a is None or not a.is_fill:
        return ("timed out" if a is not None and a.action == TIMEOUT else "passed") + f" on {turn.maker}", 0, "—"
    pnl = hand.fill_pnl(turn, a)
    if a.action == BUY:
        return f"bought {a.size} @ {a.price} from {turn.maker}", pnl, f"settle {s} {'>' if s > a.price else '≤'} {a.price}"
    return f"sold {a.size} @ {a.price} to {turn.maker}", pnl, f"settle {s} {'<' if s < a.price else '≥'} {a.price}"


def trades_table(hand: Hand) -> Table:
    reported = hand.reported is not None
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    t.add_column("TURN", no_wrap=True)
    t.add_column("YOU")
    t.add_column("$", justify="right", no_wrap=True)
    t.add_column("WHY")
    for i, turn in enumerate(hand.turns):
        what, pnl, why = trade_row(hand, turn)
        t.add_row(CIRCLED[i], what, _pnl_text(pnl) if reported else Text("?", style=DIM),
                  Text(why if reported else "", style=DIM))
    return t


def walkthrough_text(hand: Hand) -> Text:
    """Your hand P&L from the hand's real numbers: cash flows, position, then cash + position × settle."""
    out = Text()
    out.append_text(Text("settle = ") + settle_line(hand))
    cash = pos = 0
    for i, turn in enumerate(hand.turns):
        for a in turn.fills:
            if YOU not in (a.who, turn.maker):
                continue
            you_buy = (a.action == BUY) == (a.who == YOU)
            sign = 1 if you_buy else -1
            pos += sign * a.size
            cash -= sign * a.size * a.price
            other = turn.maker if a.who == YOU else a.who
            verb = f"bought {a.size} @ {a.price} from" if you_buy else f"sold {a.size} @ {a.price} to"
            out.append(f"\n{CIRCLED[i]} you {verb} {other}: cash {'−' if you_buy else '+'}{a.size}×{a.price}"
                       f" → {money(cash)}, position {pos:+d}", style=DIM)
    s, pnl = hand.settle, hand.pnl(YOU)
    out.append("\n\nP&L = cash + position × settle", style="bold")
    out.append(f"\n    = {cash} + ({pos:+d} × {s}) = ")
    out.append(str(pnl), style=f"bold {AMBER}")
    out.append(f"\nmaking {money(hand.making_pnl)} + taking {money(hand.taking_pnl)} = {money(pnl)}", style=DIM)
    return out


class SettleScreen(TradeScreen):
    BINDINGS = [Binding("enter", "next", "next hand"), Binding("w", "walkthrough", "walkthrough")]

    DEFAULT_CSS = """
    SettleScreen #right { width: 1fr; }
    SettleScreen #settle-sum { margin-top: 1; }
    SettleScreen #report-row { height: 1; margin-top: 1; }
    SettleScreen #report-hint { width: 1fr; padding-left: 2; }
    SettleScreen #report-result { margin-top: 1; }
    """

    def __init__(self, session: TradeSession) -> None:
        super().__init__()
        self.session = session
        self.hand = session.current
        self.started = 0.0

    def compose(self) -> ComposeResult:
        hand = self.hand
        ui = ui_for(self.session.config)
        yield from header(self.session, hand.balance_before, settle=True)  # new balance hidden until reported
        with TitledPanel("TABLE — SETTLE", id="table"):
            widgets = []
            for i, card in enumerate(hand.items):
                w = ui.make_widget(card, hand.SOURCE.value(card, hand.event), True, hand.event)
                w.set_class(i not in hand.face_up, "fresh")
                w.tag = "×2" if i == hand.doubled else ""
                widgets.append(w)
            yield Horizontal(*widgets, classes="cards")
            yield Static(settle_line(hand), id="settle-sum")
            yield Static(peeks_line(hand))
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("HAND LEADERBOARD", Static(id="board"), Static(
                    "zero-sum: the four hand P&Ls add up to $0", classes="dim"), double=True)
                with TitledPanel("REPORT YOUR HAND P&L", double=True, id="report"):
                    with Horizontal(id="report-row"):
                        yield Input(type="integer", placeholder="P&L", id="report-input")
                        yield Static("type your hand P&L, ⏎ to submit", id="report-hint", classes="dim")
                    yield Static(id="report-result")
            with Vertical(id="right"):
                yield TitledPanel("YOUR TRADES", Static(id="trades"))
                yield TitledPanel("WALKTHROUGH", Static(id="walk"), id="walk-panel")
        yield KeyBar([("0-9 −", "type P&L"), ("⏎", "submit")])

    def on_mount(self) -> None:
        self.query_one("#walk-panel").display = False
        self.refresh_tables()
        self.query_one("#report-input", Input).focus()
        self.started = monotonic()

    def refresh_tables(self) -> None:
        self.query_one("#board", Static).update(leaderboard(self.hand))
        self.query_one("#trades", Static).update(trades_table(self.hand))

    def on_input_submitted(self, message: Input.Submitted) -> None:
        text = message.value.strip()
        try:
            int(text)
        except ValueError:
            self.notify("enter a whole number, e.g. -7", severity="warning")
            return
        hand = self.hand
        correct = self.session.report(text, monotonic() - self.started)
        message.input.disabled = True
        self.set_focus(None)
        result = Text()
        if correct:
            result.append(f"✓ CORRECT  {money(hand.pnl(YOU))}", style=f"bold {GREEN}")
        else:
            result.append(f"✗ you said {text} — actual hand P&L is {hand.pnl(YOU)}", style=f"bold {RED}")
        result.append(f"   answered in {hand.answer_time:.1f}s", style=DIM)
        self.query_one("#report-result", Static).update(result)
        self.query_one("#report-hint", Static).update("")
        self.query_one("#walk", Static).update(walkthrough_text(hand))
        self.refresh_tables()
        self.query_one(TopBar).set(balance=self.session.balance)
        nxt = "recap" if self.session.finished else "next hand"
        self.query_one(KeyBar).set_keys([("W", "walkthrough"), ("⏎", nxt)])

    def action_walkthrough(self) -> None:
        if self.hand.reported is None:
            return
        panel = self.query_one("#walk-panel")
        panel.display = not panel.display

    def action_next(self) -> None:
        if self.hand.reported is None:
            self.query_one("#report-input", Input).focus()
            return
        self.app.switch_screen(next_screen(self.session))

