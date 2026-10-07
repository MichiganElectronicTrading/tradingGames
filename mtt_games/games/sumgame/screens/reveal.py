"""Reveal screen: everything face up, settle math, P&L self-report, then the breakdown."""

from __future__ import annotations

from time import monotonic

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Static

from mtt_games.games.sumgame.engine import BUY, PASS, SELL, Round, SumSession, to_cents
from mtt_games.games.sumgame.screens.common import (
    crumb,
    event_banner,
    item_widget,
    next_round_screen,
    round_text,
    top_bar,
)
from mtt_games.games.sumgame.stats import money
from mtt_games.games.sumgame.ui import ui_for
from mtt_games.widgets import AMBER, DIM, GREEN, RED, KeyBar, TitledPanel, TopBar, fmt_balance


def settle_line(rnd: Round) -> Text:
    parts = []
    for i, v in enumerate(rnd.values):
        s = f"({v})" if v < 0 else str(v)
        parts.append(f"2×{s}" if i == rnd.doubled else s)
    out = Text(" + ".join(parts) + " = ")
    out.append(str(rnd.settle), style=f"bold {AMBER}")
    return out


def trade_text(rnd: Round) -> Text:
    d, price = rnd.decision, rnd.SOURCE.price
    out = Text()
    if d.action == BUY:
        out.append(f"BOUGHT {d.size} @ {price(d.ask)}", style=f"bold {GREEN}")
    elif d.action == SELL:
        out.append(f"SOLD {d.size} @ {price(d.bid)}", style=f"bold {RED}")
    elif d.action == PASS:
        out.append("PASSED", style="bold")
    else:
        out.append("TIMED OUT — auto-pass", style=f"bold {RED}")
    out.append(f"\nquote {price(d.bid)} @ {price(d.ask)} · decided at {d.t:.1f}s", style=DIM)
    return out


def breakdown_text(rnd: Round) -> Text:
    d, places = rnd.decision, rnd.SOURCE.places
    rows: list[tuple[str, Text]] = []
    label = "fair at trade" if d.is_trade else "fair at decision"
    rows.append((label, Text(f"{d.fair:.2f}")))
    if d.is_trade:
        e = d.edge_per_unit
        rows.append((
            "edge/unit",
            Text(f"{e:+.2f} × {d.size} → expected {money(d.edge_dollars, 2)}", style=GREEN if e >= 0 else RED),
        ))
    else:
        buy_edge, sell_edge = d.fair - float(d.ask), float(d.bid) - d.fair
        rows.append(("best edge/unit", Text(f"{d.best_edge:+.2f} (buy {buy_edge:+.2f} · sell {sell_edge:+.2f})")))
    pnl = rnd.pnl
    rows.append(("realized", Text(money(pnl, places), style=GREEN if pnl > 0 else RED if pnl < 0 else "")))
    good = rnd.verdict.startswith(("good", "correct"))
    rows.append(("verdict", Text(rnd.verdict, style=f"bold {GREEN if good else RED}")))
    rows.append(("new balance", Text(fmt_balance(rnd.balance_after, places), style=f"bold {AMBER}")))
    out = Text()
    for i, (k, v) in enumerate(rows):
        if i:
            out.append("\n")
        out.append(f"{k:<17}", style=DIM)
        out.append_text(v)
    return out


def explain_text(rnd: Round) -> Text:
    src = rnd.SOURCE
    m = rnd.decision.market
    out = Text()
    if m.hidden == 0:
        out.append(f"face up {m.up_sum} = {m.fair:.2f}", style="bold")
        out.append(f"\nno hidden {src.noun}, so fair is just the face-up sum", style=DIM)
    else:
        mult = f"({m.hidden}+1)" if m.double_hidden else str(m.hidden)
        out.append(f"face up {m.up_sum} + {mult} × {src.mean_label} {m.deck_mean:.2f} = {m.fair:.2f}", style="bold")
        out.append("\n")
        for note in src.explain_notes(m):
            out.append(f"\n· {note}", style=DIM)
    if rnd.event:
        out.append(f"\n· {src.event_note(rnd.event)}", style=AMBER)
    return out


class RevealScreen(Screen):
    BINDINGS = [
        Binding("enter", "next", "next round"),
        Binding("w", "explain", "explain fair"),
    ]

    DEFAULT_CSS = """
    RevealScreen #reveal-body { height: 1fr; }
    RevealScreen #reveal-left { width: 1fr; }
    RevealScreen #reveal-right { width: 1fr; }
    RevealScreen #cards { height: auto; margin-top: 1; }
    RevealScreen #settle { margin-top: 1; }
    RevealScreen #report-row { height: 1; margin-top: 1; }
    RevealScreen #report-hint { width: 1fr; padding-left: 2; }
    RevealScreen #report-result { margin-top: 1; }
    """

    def __init__(self, session: SumSession) -> None:
        super().__init__()
        self.session = session
        self.ui = ui_for(session)
        self.src = session.source
        self.rnd = session.current
        self.started = 0.0

    @property
    def whole_dollars(self) -> bool:
        return self.src.places == 0

    def compose(self) -> ComposeResult:
        s, r = self.session, self.rnd
        yield top_bar(self.src, crumb(s), round_text(s, r), r.balance_before)  # new balance hidden until reported
        if r.event:
            yield Static(event_banner(self.src, r.event), classes="event-banner")
        hidden = set(r.hidden)
        with TitledPanel("TABLE — REVEAL", id="table"):
            with Horizontal(id="cards"):
                for i in range(len(r.items)):
                    w = item_widget(self.ui, r, i, True)
                    w.set_class(i in hidden, "fresh")
                    w.tag = "×2" if i == r.doubled else ""
                    yield w
            yield Static(settle_line(r), id="settle")
        hint = "type your round P&L, ⏎ to submit" + ("" if self.whole_dollars else " (to the cent, e.g. -3.25)")
        with Horizontal(id="reveal-body"):
            with Vertical(id="reveal-left"):
                yield TitledPanel("YOUR TRADE", Static(trade_text(r)))
                with TitledPanel("REPORT YOUR P&L", double=True, id="report"):
                    with Horizontal(id="report-row"):
                        kind = "integer" if self.whole_dollars else "number"
                        yield Input(type=kind, placeholder="P&L", id="report-input")
                        yield Static(hint, id="report-hint", classes="dim")
                    yield Static(id="report-result")
            with Vertical(id="reveal-right"):
                yield TitledPanel("BREAKDOWN", Static(id="breakdown"), id="breakdown-panel")
                yield TitledPanel("FAIR VALUE", Static(id="explain"), id="explain-panel")
        yield KeyBar([("0-9 -" if self.whole_dollars else "0-9 . -", "type P&L"), ("⏎", "submit")])

    def on_mount(self) -> None:
        self.query_one("#breakdown-panel").display = False
        self.query_one("#explain-panel").display = False
        self.query_one("#report-input", Input).focus()
        self.started = monotonic()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        text = message.value.strip()
        try:
            if self.whole_dollars:
                int(text)
            else:
                to_cents(text)
        except ValueError:
            example = "-7" if self.whole_dollars else "-3.25"
            self.notify(f"enter a number, e.g. {example}", severity="warning")
            return
        r, price = self.rnd, self.src.price
        correct = self.session.report(text, monotonic() - self.started)
        message.input.disabled = True
        self.set_focus(None)

        result = Text()
        if correct:
            result.append(f"✓ CORRECT  {money(r.pnl, self.src.places)}", style=f"bold {GREEN}")
        else:
            result.append(f"✗ you said {text} — actual P&L is {price(r.pnl)}", style=f"bold {RED}")
        result.append(f"   answered in {r.answer_time:.1f}s", style=DIM)
        self.query_one("#report-result", Static).update(result)
        self.query_one("#report-hint", Static).update("")

        self.query_one("#breakdown", Static).update(breakdown_text(r))
        self.query_one("#breakdown-panel").display = True
        self.query_one("#explain", Static).update(explain_text(r))
        self.query_one(TopBar).set(balance=self.session.balance)
        nxt = "recap" if self.session.finished else "next round"
        self.query_one(KeyBar).set_keys([("W", "explain fair value"), ("⏎", nxt)])

    def action_explain(self) -> None:
        if self.rnd.reported is None:
            return
        panel = self.query_one("#explain-panel")
        panel.display = not panel.display

    def action_next(self) -> None:
        if self.rnd.reported is None:
            self.query_one("#report-input", Input).focus()
            return
        self.app.switch_screen(next_round_screen(self.session))
