"""Round screens: the forced open / response, the open outcry, and the round close (reveal)."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static

from mtt_games.games.outcry.commands import CHEAT_SHEET
from mtt_games.games.outcry.engine import CLOSED, OPEN, OPEN_KIND, OUTCRY, RESPOND, TICK, YOU, PublicState
from mtt_games.games.outcry.model import HIGHEST, LOWEST
from mtt_games.games.outcry.screens.common import (
    OutcryScreen,
    big,
    clock_text,
    know_text,
    refresh_top_bar,
    reveals_text,
    seat_line,
    signed,
    table_strip,
    top_bar,
)
from mtt_games.games.outcry.traders import BUY, PASS, SELL
from mtt_games.games.sumgame.screens.round import quote_text
from mtt_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, KeyButton, TitledPanel

HISTORY_LINES = 4
BOOK_LEVELS = 6
TAPE_LINES = 12


def _int(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def table_panel(game) -> TitledPanel:
    return TitledPanel("TABLE", Static(table_strip(game), id="strip"), Static(reveals_text(game), id="revealed"),
                       id="table")


# ── forced open / response ──────────────────────────────────────────────────


class OpenScreen(OutcryScreen):
    PHASES = (OPEN, RESPOND)
    BINDINGS = [
        Binding("b", "respond('buy')", "buy"),
        Binding("s", "respond('sell')", "sell"),
        Binding("p", "respond('pass')", "pass"),
    ]

    DEFAULT_CSS = """
    OpenScreen #quote { width: 100%; text-align: center; margin-top: 1; }
    OpenScreen #buttons { height: 1; margin-top: 1; }
    OpenScreen #fields { height: auto; margin-top: 1; }
    OpenScreen .field { width: 1fr; height: auto; margin-right: 2; }
    OpenScreen .field Input { width: 100%; }
    OpenScreen .field-label { text-style: bold; color: #5FD4E0; }
    OpenScreen .big { height: 5; margin-top: 1; }
    OpenScreen #width-line { margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        g = self.game
        r = g.round
        yield top_bar(g, "OPEN")
        yield table_panel(g)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                if g.phase == RESPOND:
                    size = g.config.trade_size
                    with TitledPanel(f"{g.names[r.opener]} OPENS — YOU MUST RESPOND", double=True, id="market"):
                        yield Static(quote_text(str(r.bid), str(r.ask)), id="quote")
                        with Horizontal(id="buttons"):
                            yield KeyButton(f"[B] BUY {size} @ {r.ask}", id="buy", classes="buy")
                            yield KeyButton(f"[S] SELL {size} @ {r.bid}", id="sell", classes="sell")
                            yield KeyButton("[P] PASS", id="pass")
                        yield Static("everyone answers blind and at once · timer runs out = pass", classes="dim")
                else:
                    with TitledPanel("YOUR FORCED OPEN", double=True, id="market"):
                        with Horizontal(id="fields"):
                            for key, label in (("bid", "BID"), ("ask", "ASK")):
                                with Vertical(classes="field"):
                                    yield Static(label, classes="field-label")
                                    yield Input(type="integer", id=f"in-{key}", placeholder=label.lower())
                                    yield Static(id=f"big-{key}", classes="big")
                        yield Static(id="width-line")
                        yield Static(id="open-error")
                        yield KeyButton("⏎ OPEN", id="open", classes="buy")
                        yield Static(f"{g.config.trade_size} lot each way to everyone · timer runs out = auto-quote",
                                     classes="dim")
            with Vertical(id="right"):
                yield TitledPanel("TIMER", Static(id="timer", classes="timer"))
                yield TitledPanel("WHAT YOU KNOW", Static(id="know"))
        keys = [("B", "buy @ ask"), ("S", "sell @ bid"), ("P", "pass")] if g.phase == RESPOND else [
            ("0-9", "type"), ("Tab", "next field"), ("⏎", "open")]
        yield KeyBar(keys)

    def on_mount(self) -> None:
        super().on_mount()
        if self.game.phase == OPEN:
            self.query_one("#in-bid", Input).focus()
            self.refresh_open()

    def refresh_view(self) -> None:
        g = self.game
        self.query_one("#timer", Static).update(clock_text(g.seconds_left(), g.config.respond_s))
        self.query_one("#know", Static).update(know_text(g))

    # ── responding ──────────────────────────────────────────────────────────

    def action_respond(self, action: str) -> None:
        if self.leaving or self.game.phase != RESPOND:
            return
        self.sync()
        if self.game.phase == RESPOND:
            self.game.player_respond(action)
            self.leave()

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        if message.button.id == "open":
            self.submit_open()
        else:
            self.action_respond({"buy": BUY, "sell": SELL, "pass": PASS}[message.button.id])

    # ── opening ─────────────────────────────────────────────────────────────

    def quote(self) -> tuple[int | None, int | None]:
        return _int(self.query_one("#in-bid", Input).value), _int(self.query_one("#in-ask", Input).value)

    def refresh_open(self) -> None:
        bid, ask = self.quote()
        for key, v, color in (("bid", bid, GREEN), ("ask", ask, RED)):
            self.query_one(f"#big-{key}", Static).update(big("" if v is None else str(v), f"bold {color}"))
        line = Text("width ", style=DIM)
        line.append("—" if bid is None or ask is None else str(ask - bid), style="bold")
        self.query_one("#width-line", Static).update(line)

    def on_input_changed(self, message: Input.Changed) -> None:
        self.query_one("#open-error", Static).update("")
        self.refresh_open()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        self.submit_open()

    def submit_open(self) -> None:
        if self.leaving:
            return
        self.sync()
        if self.game.phase != OPEN:
            return
        bid, ask = self.quote()
        errs = ["enter a whole-number bid and ask"] if None in (bid, ask) else self.game.open_errors(bid, ask)
        if errs:
            self.query_one("#open-error", Static).update(Text(f"✗ {errs[0]}", style=f"bold {RED}"))
            self.app.bell()
            return
        self.game.player_open(bid, ask)
        self.leave()


# ── the open outcry ─────────────────────────────────────────────────────────


def ladder(state: PublicState) -> Table:
    """BOOK: bidder names | price | offerer names. Best bid/offer highlighted, your orders in amber."""
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    t.add_column("BIDS", justify="right", ratio=2)
    t.add_column("PRICE", justify="center", ratio=1, no_wrap=True)
    t.add_column("OFFERS", justify="left", ratio=2)

    def names(orders: tuple[tuple[str, int], ...], price: int) -> Text:
        out = Text()
        for i, (who, p) in enumerate(o for o in orders if o[1] == price):
            if i:
                out.append(" ")
            out.append(who, style=f"bold {AMBER}" if who == "YOU" else "")
        return out

    offer_prices = sorted({p for _, p in state.offers})[:BOOK_LEVELS]
    bid_prices = sorted({p for _, p in state.bids}, reverse=True)[:BOOK_LEVELS]
    for p in reversed(offer_prices):
        best = p == offer_prices[0]
        t.add_row("", Text(str(p), style=f"bold {RED}"), names(state.offers, p),
                  style=f"on #2A1A1E" if best else None)
    if offer_prices and bid_prices:
        t.add_row(Text("── spread", style=DIM), Text(str(offer_prices[0] - bid_prices[0]), style="bold"),
                  Text("──", style=DIM))
    else:
        t.add_row(Text("── one-sided" if offer_prices or bid_prices else "── no orders", style=DIM), "",
                  Text("──", style=DIM))
    for p in bid_prices:
        best = p == bid_prices[0]
        t.add_row(names(state.bids, p), Text(str(p), style=f"bold {GREEN}"), "",
                  style=f"on #16281C" if best else None)
    return t


def responses_line(game) -> Text:
    r = game.round
    out = Text()
    out.append(f"OPEN {game.names[r.opener]} {r.bid} @ {r.ask}", style=f"bold {AMBER}")
    if r.auto_quoted:
        out.append(" (auto-quoted for you)", style=DIM)
    words = {BUY: "bought", SELL: "sold", PASS: "passed", "timeout": "timed out"}
    for x in r.responses:
        out.append(" · ", style=DIM)
        out.append(f"{game.names[x.seat]} {words[x.action]}" + ("" if x.applied else " (skipped: limit)"),
                   style="" if x.applied else RED)
    return out


def tape_text(game) -> Text:
    r = game.round
    out = responses_line(game)
    trades = [t for t in game.trades if t.round == r.number and t.kind != OPEN_KIND]
    if not trades:
        out.append("\nno outcry trades yet", style=DIM)
    for t in reversed(trades[-TAPE_LINES:]):
        secs = (t.at - r.outcry_start) * TICK
        lifted = t.aggressor == t.buyer
        who, other = game.names[t.aggressor], game.names[t.seller if lifted else t.buyer]
        out.append(f"\n{int(secs) // 60}:{int(secs) % 60:02d}  ", style=DIM)
        out.append(f"{who:<7}", style=f"bold {AMBER}" if who == "YOU" else "bold")
        out.append(" lifts " if lifted else " hits  ", style=GREEN if lifted else RED)
        out.append(f"{other:<7}", style=f"bold {AMBER}" if other == "YOU" else "")
        out.append(f" {t.price}", style="bold")
    return out


def orders_text(game) -> Text:
    you = game.you()
    out = Text()
    out.append("bid    ", style=DIM)
    out.append(str(you.bid) if you.bid is not None else "—", style=f"bold {GREEN}" if you.bid is not None else DIM)
    out.append("\noffer  ", style=DIM)
    out.append(str(you.offer) if you.offer is not None else "—", style=f"bold {RED}" if you.offer is not None else DIM)
    out.append("\nposition ", style=DIM)
    out.append(f"{signed(you.position)} / ±{game.config.limit}", style="bold")
    last = game.public().last_price
    out.append("\nlast trade ", style=DIM)
    out.append(str(last) if last is not None else "—", style="bold")
    return out


class TradingScreen(OutcryScreen):
    """The open outcry: book, tape, your orders, and the command line."""

    PHASES = (OUTCRY,)
    BINDINGS = [
        Binding("up", "recall", "recall", priority=True),
        Binding("ctrl+b", "quick('buy')", "buy", priority=True),
        Binding("ctrl+s", "quick('sell')", "sell", priority=True),
        Binding("escape", "quick('x')", "cancel all", priority=True),
    ]

    DEFAULT_CSS = """
    TradingScreen #seats { height: 1; background: #1C232C; }
    TradingScreen #book-panel { height: 1fr; }
    TradingScreen #tape-panel { height: 1fr; }
    TradingScreen #command { height: auto; }
    TradingScreen #history { height: 4; }
    TradingScreen #cmd { width: 100%; }
    """

    def __init__(self, game) -> None:
        super().__init__(game)
        self.history: list[Text] = []
        self.last_command = ""

    def compose(self) -> ComposeResult:
        yield top_bar(self.game, "OUTCRY")
        yield Static(id="seats")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("BOOK", Static(id="book"), id="book-panel", double=True)
                yield TitledPanel("TAPE", Static(id="tape"), id="tape-panel")
            with Vertical(id="right"):
                yield TitledPanel("TIMER", Static(id="timer", classes="timer"))
                yield TitledPanel("YOUR ORDERS", Static(id="orders"))
                yield TitledPanel("WHAT YOU KNOW", Static(id="know"))
        with TitledPanel("COMMAND", id="command", double=True):
            yield Static(id="history")
            yield Input(id="cmd", placeholder="b 464 · o 467 · 464 @ 467 · buy · sell · x")
            yield Static(CHEAT_SHEET, classes="dim")
        yield KeyBar([("⏎", "send"), ("↑", "recall"), ("^B", "buy"), ("^S", "sell"), ("Esc", "cancel all")])

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#cmd", Input).focus()

    def refresh_view(self) -> None:
        g = self.game
        state = g.public()
        refresh_top_bar(self, g)
        self.query_one("#seats", Static).update(seat_line(g))
        self.query_one("#book", Static).update(ladder(state))
        self.query_one("#tape", Static).update(tape_text(g))
        self.query_one("#timer", Static).update(clock_text(g.seconds_left(), g.config.outcry_s))
        self.query_one("#orders", Static).update(orders_text(g))
        self.query_one("#know", Static).update(know_text(g))
        history = Text("\n").join(self.history[-HISTORY_LINES:]) if self.history else Text(
            "type a command and press ⏎", style=DIM)
        self.query_one("#history", Static).update(history)

    def run(self, text: str) -> None:
        if self.leaving:
            return
        self.sync()  # act at the current time
        if self.leaving:
            return
        echoes = self.game.command(text)
        if text.strip():
            self.last_command = text.strip()
        for e in echoes:
            self.history.append(Text(f"> {text.strip()}  ", style=DIM) + Text(e.text, style=GREEN if e.ok else RED))
        self.refresh_view()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        text = message.value
        message.input.value = ""
        self.run(text)

    def action_recall(self) -> None:
        cmd = self.query_one("#cmd", Input)
        cmd.value = self.last_command
        cmd.cursor_position = len(cmd.value)

    def action_quick(self, command: str) -> None:
        self.run(command)


# ── round close ──────────────────────────────────────────────────────────────


def your_round_text(game, number: int) -> Text:
    out = Text()
    trades = [t for t in game.trades if t.round == number and YOU in (t.buyer, t.seller)]
    if not trades:
        return Text("no trades this round", style=DIM)
    for t in trades:
        buying = t.buyer == YOU
        other = game.names[t.seller if buying else t.buyer]
        when = "open" if t.kind == OPEN_KIND else "outcry"
        if out:
            out.append("\n")
        out.append(f"{when:<7}", style=DIM)
        out.append("BOUGHT " if buying else "SOLD   ", style=f"bold {GREEN if buying else RED}")
        out.append(f"{t.size} @ {t.price} ", style="bold")
        out.append(f"{'from' if buying else 'to'} {other}", style=DIM)
    return out


class CloseScreen(OutcryScreen):
    """The round closes: orders are wiped and one hidden number turns over (anonymously)."""

    PHASES = (CLOSED,)
    BINDINGS = [Binding("enter", "next", "next")]

    DEFAULT_CSS = """
    CloseScreen #reveal-value { height: 5; margin: 1 0; }
    """

    def compose(self) -> ComposeResult:
        g = self.game
        r = g.round
        seen = g.you().reveals[-1]
        yield top_bar(g, "REVEAL")
        yield table_panel(g)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                head = Text("a hidden number turns over", style=DIM)
                if seen.label == LOWEST:
                    line = Text(f"LOWEST NUMBER: {seen.value}", style=f"bold {AMBER}")
                elif seen.label == HIGHEST:
                    line = Text(f"HIGHEST NUMBER: {seen.value}", style=f"bold {AMBER}")
                else:
                    line = Text(f"a hidden number: {seen.value}", style="bold")
                if seen.mine:
                    line.append("  (yours — that was your own number)", style=f"bold {GREEN}")
                yield TitledPanel("REVEAL", Static(head), Static(big(str(seen.value), f"bold {AMBER}"), id="reveal-value"),
                                  Static(line, id="reveal-line"), double=True)
                yield TitledPanel(f"YOUR ROUND {r.number}", Static(your_round_text(g, r.number)))
            with Vertical(id="right"):
                yield TitledPanel("WHAT YOU KNOW", Static(know_text(g)))
                yield TitledPanel("NEXT", Static(self.next_text()))
        yield KeyBar([("⏎", "next round" if len(g.rounds) < g.config.rounds else "final reveal")])

    def next_text(self) -> Text:
        g = self.game
        if len(g.rounds) >= g.config.rounds:
            return Text("FINAL REVEAL — then work out your P&L", style=f"bold {AMBER}")
        opener = g.setup.openers[len(g.rounds)]
        who = "YOU open" if opener == YOU else f"{g.names[opener]} opens"
        out = Text(f"ROUND {len(g.rounds) + 1}: {who}", style=f"bold {AMBER}")
        out.append("\n⏎ continue", style=DIM)
        return out

    def action_next(self) -> None:
        if not self.leaving:
            self.game.next_round()
            self.leave()

