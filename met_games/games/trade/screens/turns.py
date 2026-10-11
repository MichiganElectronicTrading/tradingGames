"""The turn screens: your market (MakeScreen), its fills (FillsScreen), and a computer trader's
market that you act on first (TakeScreen)."""

from __future__ import annotations

from time import monotonic

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static

from met_games.games.sumgame.engine import BUY, PASS, SELL, TIMEOUT
from met_games.games.sumgame.screens.round import quote_text
from met_games.games.trade.engine import TURNS, YOU, Action, TradeSession, Turn
from met_games.games.trade.screens.common import (
    TradeScreen,
    TurnBar,
    advance,
    big_number,
    clock_text,
    header,
    markets_table,
    next_label,
    position_text,
    standings_table,
    table_panel,
    traders_text,
)
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, KeyButton, TitledPanel

FEED_STEP = 0.6  # seconds per line of the fills feed
FIELDS = (("bid", "BID", "you buy here"), ("ask", "ASK", "you sell here"), ("size", "SIZE", "per side"))


def _int(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def _ok(good: bool) -> Text:
    return Text(" ✓", style=f"bold {GREEN}") if good else Text(" ✗", style=f"bold {RED}")


# ── your market ──────────────────────────────────────────────────────────────


class MakeScreen(TradeScreen):
    DEFAULT_CSS = """
    MakeScreen #right { width: 40; }
    MakeScreen #fields { height: auto; margin-top: 1; }
    MakeScreen .field { width: 1fr; height: auto; margin-right: 2; }
    MakeScreen .field Input { width: 100%; }
    MakeScreen .field-label { text-style: bold; color: #5FD4E0; }
    MakeScreen .big { height: 5; margin-top: 1; }
    MakeScreen #width-line { margin-top: 1; }
    MakeScreen #timer { text-align: center; }
    """

    def __init__(self, session: TradeSession) -> None:
        super().__init__()
        self.session = session
        self.hand = session.current
        self.cfg = session.config
        self.done = False
        self.started = 0.0

    def compose(self) -> ComposeResult:
        yield from header(self.session, self.session.balance)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield table_panel(self.session)
                with TitledPanel("YOUR MARKET", double=True, id="market"):
                    with Horizontal(id="fields"):
                        for key, label, caption in FIELDS:
                            with Vertical(classes="field"):
                                yield Static(f"{label}  ", classes="field-label")
                                yield Input(type="integer", id=f"in-{key}", placeholder=caption)
                                yield Static(id=f"big-{key}", classes="big")
                    yield Static(id="width-line")
                    yield Static(id="risk-line")
                    yield Static(id="quote-error")
                    yield KeyButton("⏎ SHOW MARKET", id="show", classes="buy")
            with Vertical(id="right"):
                yield TitledPanel("TIMER", Static(id="timer"))
                yield TitledPanel("TABLE", Static(traders_text(self.hand, self.cfg.peeks)))
                yield TitledPanel("STANDINGS", Static(standings_table(self.session)))
        yield KeyBar([("0-9 −", "type"), ("Tab", "next field"), ("⏎", "show market")])

    def on_mount(self) -> None:
        size = self.query_one("#in-size", Input)
        size.value = str(self.cfg.FIXED_SIZE)
        size.disabled = self.cfg.sizing == "fixed"
        self.query_one("#in-bid", Input).focus()
        self.started = monotonic()
        self.refresh_quote()
        self.refresh_clock(0.0)
        self.ticker = self.set_interval(0.1, self.tick)

    # ── clock ───────────────────────────────────────────────────────────────

    def tick(self) -> None:
        if self.done:
            return
        t = monotonic() - self.started
        if t >= self.cfg.quote_timer_s:
            self.session.no_quote()
            self.finish()
            return
        self.refresh_clock(t)

    def refresh_clock(self, t: float) -> None:
        self.query_one("#timer", Static).update(clock_text(self.cfg.quote_timer_s - t, self.cfg.quote_timer_s))

    # ── quote ───────────────────────────────────────────────────────────────

    def values(self) -> tuple[int | None, int | None, int | None]:
        bid, ask, size = (_int(self.query_one(f"#in-{key}", Input).value) for key, _, _ in FIELDS)
        return bid, ask, size

    def refresh_quote(self) -> None:
        bid, ask, size = self.values()
        for (key, _, _), v, color in zip(FIELDS, (bid, ask, size), (GREEN, RED, AMBER)):
            self.query_one(f"#big-{key}", Static).update(big_number("" if v is None else str(v), f"bold {color}"))

        cfg = self.cfg
        line = Text("width ", style=DIM)
        if bid is None or ask is None:
            line.append("—", style="bold")
            line.append(f" · allowed {cfg.width_min}–{cfg.width_max}", style=DIM)
        else:
            w = ask - bid
            line.append(str(w), style="bold")
            line.append(f" · allowed {cfg.width_min}–{cfg.width_max}", style=DIM)
            line.append_text(_ok(cfg.width_min <= w <= cfg.width_max))
        self.query_one("#width-line", Static).update(line)

        risk = Text("worst case ", style=DIM)
        if None in (bid, ask, size) or size < 1:
            risk.append("— enter bid, ask and size", style=DIM)
        else:
            cases = self.session.quote_risk(bid, ask, size)
            risk.append(" · ".join(f"{case} −${loss}" for case, loss in cases))
            risk.append(f" · limit ${self.session.balance}", style=DIM)
            risk.append_text(_ok(max(loss for _, loss in cases) <= self.session.balance))
        self.query_one("#risk-line", Static).update(risk)

    def on_input_changed(self, message: Input.Changed) -> None:
        self.query_one("#quote-error", Static).update("")
        self.refresh_quote()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        self.submit()

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        self.submit()

    def submit(self) -> None:
        if self.done:
            return
        bid, ask, size = self.values()
        if None in (bid, ask, size):
            errs = ["enter a whole-number bid, ask and size"]
        else:
            errs = self.session.quote_errors(bid, ask, size)
        if errs:
            self.query_one("#quote-error", Static).update(Text(f"✗ {errs[0]}", style=f"bold {RED}"))
            self.app.bell()
            return
        self.session.post_quote(bid, ask, size)
        self.finish()

    def finish(self) -> None:
        self.done = True
        self.ticker.stop()
        self.app.switch_screen(FillsScreen(self.session))


# ── your market's fills ──────────────────────────────────────────────────────


def feed_rows(session: TradeSession, turn: Turn) -> list[tuple[str, str, str, str, int]]:
    """(TIME, WHO, ACTION, FILL, YOUR POSITION) for each trader's action on your market."""
    hand = session.current
    pos = hand.position[YOU] - sum(-a.size if a.action == BUY else a.size for a in turn.fills)
    bid_f = ask_f = 0
    rows = []
    for i, a in enumerate(turn.actions):
        if a.action == BUY:
            pos -= a.size
            ask_f += a.size
            action, fill = f"buys {a.size} @ {a.price}", f"ask {ask_f}/{turn.size}"
        elif a.action == SELL:
            pos += a.size
            bid_f += a.size
            action, fill = f"sells {a.size} @ {a.price}", f"bid {bid_f}/{turn.size}"
        else:
            gone = {BUY: " — ask gone", SELL: " — bid gone"}.get(a.wanted or "", "")
            action, fill = f"passes{gone}", "—"
        rows.append((f"{(i + 1) * FEED_STEP:.1f}s", a.who, action, fill, pos))
    return rows


def learned_line(a: Action, turn: Turn) -> Text:
    out = Text(f"{a.who:<6} ", style="bold")
    if a.action == BUY:
        out.append(f"bought above → values it ≥ {turn.ask + 1}", style=GREEN)
    elif a.action == SELL:
        out.append(f"sold below → values it ≤ {turn.bid - 1}", style=RED)
    elif a.wanted == BUY:
        out.append(f"wanted your ask, it was gone → values it ≥ {turn.ask + 1}", style=GREEN)
    elif a.wanted == SELL:
        out.append(f"wanted your bid, it was gone → values it ≤ {turn.bid - 1}", style=RED)
    else:
        out.append(f"passed inside → values it between {turn.bid - 1} and {turn.ask + 1}", style=DIM)
    return out


class FillsScreen(TradeScreen):
    BINDINGS = [Binding("enter", "next", "next")]

    DEFAULT_CSS = """
    FillsScreen #right { width: 56; }
    FillsScreen #feed-footer { margin-top: 1; }
    """

    def __init__(self, session: TradeSession) -> None:
        super().__init__()
        self.session = session
        self.hand = session.current
        self.turn = self.hand.turn
        self.rows = feed_rows(session, self.turn)
        self.shown = 0
        self.ticker = None

    def compose(self) -> ComposeResult:
        yield from header(self.session, self.session.balance)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel("YOUR MARKET", Static(self.summary()))
                yield TitledPanel("FILLS", Static(id="feed"), Static(id="feed-footer"), double=True)
            with Vertical(id="right"):
                yield TitledPanel("WHAT YOU LEARNED", Static(id="learned"))
                nxt = Text(next_label(self.hand), style=f"bold {AMBER}")
                nxt.append("\n⏎ continue", style=DIM)
                yield TitledPanel("NEXT", Static(nxt))
        yield KeyBar([("⏎", "skip")])

    def on_mount(self) -> None:
        if self.rows:
            self.ticker = self.set_interval(FEED_STEP, self.step)
        self.refresh_feed()

    def summary(self) -> Text:
        t = self.turn
        if not t.posted:
            return Text("no market — your quote timer ran out", style=f"bold {RED}")
        out = Text("you made ", style=DIM)
        out.append(f"{t.bid} @ {t.ask}", style=f"bold {AMBER}")
        out.append(f" · size {t.size} per side · width {t.width}", style=DIM)
        return out

    def step(self) -> None:
        self.shown += 1
        if self.shown >= len(self.rows) and self.ticker is not None:
            self.ticker.stop()
        self.refresh_feed()

    @property
    def complete(self) -> bool:
        return self.shown >= len(self.rows)

    def refresh_feed(self) -> None:
        t = self.turn
        feed = self.query_one("#feed", Static)
        if not t.posted:
            feed.update(Text("You posted no market, so the turn passes with no trades.", style=DIM))
            self.query_one("#learned", Static).update(Text("nothing — no market was posted", style=DIM))
            self.query_one(KeyBar).set_keys([("⏎", "continue")])
            return
        table = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True,
                      pad_edge=False)
        for col in ("TIME", "WHO", "ACTION", "FILL", "YOUR POSITION"):
            table.add_column(col, justify="right" if col in ("TIME", "YOUR POSITION") else "left", no_wrap=True)
        for time, who, action, fill, pos in self.rows[: self.shown]:
            style = GREEN if "sells" in action else RED if "buys" in action else DIM
            table.add_row(time, who, Text(action, style=style), fill, f"{pos:+d}")
        feed.update(table)

        learned = Text()
        for i, a in enumerate(t.actions[: self.shown]):
            if i:
                learned.append("\n")
            learned.append_text(learned_line(a, t))
        self.query_one("#learned", Static).update(learned or Text("watching…", style=DIM))

        footer = self.query_one("#feed-footer", Static)
        if self.complete:
            bf, af = t.bid_filled, t.ask_filled
            trips = min(bf, af)
            line = Text(f"bid filled {bf}/{t.size} · ask filled {af}/{t.size} · ")
            line.append(f"round trips {trips} × width {t.width} = locked ${trips * t.width}", style=f"bold {GREEN}")
            line.append(" · open position ")
            line.append(f"{bf - af:+d}", style=f"bold {AMBER}")
            footer.update(line)
            self.query_one(KeyBar).set_keys([("⏎", "continue")])
        else:
            footer.update(Text("traders are looking at your market…", style=DIM))

    def action_next(self) -> None:
        if not self.complete:
            self.shown = len(self.rows)
            if self.ticker is not None:
                self.ticker.stop()
            self.refresh_feed()
            return
        advance(self.app, self.session)


# ── a computer trader's market ──────────────────────────────────────────────


class TakeScreen(TradeScreen):
    BINDINGS = [
        Binding("b", "act('buy')", "buy"),
        Binding("s", "act('sell')", "sell"),
        Binding("p", "act('pass')", "pass"),
        Binding("left", "size(-1)", show=False),
        Binding("right", "size(1)", show=False),
        Binding("enter", "next", "next"),
    ]

    DEFAULT_CSS = """
    TakeScreen #right { width: 52; }
    TakeScreen #quote, TakeScreen #quote-size { width: 100%; text-align: center; }
    TakeScreen #buttons { height: 1; margin-top: 1; }
    TakeScreen #buttons KeyButton { margin-right: 1; }
    TakeScreen #timer { text-align: center; }
    TakeScreen #markets-panel { height: 1fr; }
    """

    def __init__(self, session: TradeSession) -> None:
        super().__init__()
        self.session = session
        self.hand = session.current
        self.turn = self.hand.turn
        self.cfg = session.config
        self.order_size = 1
        self.acted = False
        self.started = 0.0

    def compose(self) -> ComposeResult:
        t = self.turn
        yield from header(self.session, self.session.balance)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield table_panel(self.session)
                yield TitledPanel("MARKETS SO FAR", Static(id="markets"), id="markets-panel")
            with Vertical(id="right"):
                yield TitledPanel(
                    f"{t.maker}'S MARKET", Static(quote_text(str(t.bid), str(t.ask)), id="quote"),
                    Static(id="quote-size", classes="dim"), double=True, id="market",
                )
                with TitledPanel("YOUR ORDER", id="order"):
                    yield Static(id="size-line")
                    with Horizontal(id="buttons"):
                        yield KeyButton(id="buy", classes="buy")
                        yield KeyButton(id="sell", classes="sell")
                        yield KeyButton("[P] PASS", id="pass")
                    yield Static("you act first · others trade after you", id="order-note", classes="dim")
                yield TitledPanel("TIMER", Static(id="timer"))
                yield TitledPanel("YOUR POSITION", Static(id="position"))
        yield KeyBar([("B", "buy @ ask"), ("S", "sell @ bid"), ("P", "pass"), ("←→", "size ±1")])

    def on_mount(self) -> None:
        self.started = monotonic()
        self.refresh_state()
        self.refresh_clock(0.0)
        self.ticker = self.set_interval(0.1, self.tick)

    # ── clock ───────────────────────────────────────────────────────────────

    def tick(self) -> None:
        if self.acted:
            return
        t = monotonic() - self.started
        if t >= self.cfg.take_timer_s:
            self.session.timeout()
            self.after_act()
            return
        self.refresh_clock(t)

    def refresh_clock(self, t: float) -> None:
        self.query_one("#timer", Static).update(clock_text(self.cfg.take_timer_s - t, self.cfg.take_timer_s))

    # ── order ───────────────────────────────────────────────────────────────

    def sizes(self) -> tuple[int, int, int, int]:
        """(max_buy, max_sell, buy size, sell size) after clamping the chosen size to each side."""
        if self.acted:
            return 0, 0, 0, 0
        max_buy, max_sell = self.session.take_limits()
        self.order_size = max(1, min(self.order_size, max(max_buy, max_sell, 1)))
        return max_buy, max_sell, max(1, min(self.order_size, max_buy)), max(1, min(self.order_size, max_sell))

    def refresh_state(self) -> None:
        t = self.turn
        self.query_one("#markets", Static).update(markets_table(self.hand))
        self.query_one("#quote-size", Static).update(f"size  bid {t.bid_left}/{t.size} · ask {t.ask_left}/{t.size}")
        self.query_one("#position", Static).update(position_text(self.session))
        max_buy, max_sell, buy_n, sell_n = self.sizes()
        line = Text("size  ")
        line.append(f"◂ {self.order_size} ▸", style=f"bold {AMBER}")
        line.append(f" units (max buy {max_buy} · max sell {max_sell})", style=DIM)
        self.query_one("#size-line", Static).update(line)
        buy, sell = self.query_one("#buy", KeyButton), self.query_one("#sell", KeyButton)
        buy.update(f"[B] BUY {buy_n} @ {t.ask}" if max_buy else f"[B] BUY @ {t.ask}")
        sell.update(f"[S] SELL {sell_n} @ {t.bid}" if max_sell else f"[S] SELL @ {t.bid}")
        buy.disabled, sell.disabled = max_buy < 1, max_sell < 1
        self.query_one("#pass", KeyButton).disabled = self.acted

    def action_size(self, delta: int) -> None:
        if not self.acted:
            self.order_size += delta
            self.refresh_state()

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        self.action_act(message.button.id)

    def action_act(self, action: str) -> None:
        if self.acted:
            return
        if monotonic() - self.started >= self.cfg.take_timer_s:
            self.tick()
            return
        max_buy, max_sell, buy_n, sell_n = self.sizes()
        if action == PASS:
            self.session.pass_()
        elif action == BUY and max_buy >= 1:
            self.session.take(BUY, buy_n)
        elif action == SELL and max_sell >= 1:
            self.session.take(SELL, sell_n)
        else:
            self.app.bell()
            return
        self.after_act()

    def after_act(self) -> None:
        self.acted = True
        self.ticker.stop()
        self.refresh_state()
        self.query_one(TurnBar).refresh_bar()
        mine = self.turn.action_of(YOU)
        note = Text(f"you {'timed out' if mine.action == TIMEOUT else 'acted'} · the others traded after you",
                    style=DIM)
        self.query_one("#order-note", Static).update(note)
        last = len(self.hand.turns) == TURNS
        self.query_one(KeyBar).set_keys([("⏎", "settle" if last else "next turn")])

    def action_next(self) -> None:
        if self.acted:
            advance(self.app, self.session)
