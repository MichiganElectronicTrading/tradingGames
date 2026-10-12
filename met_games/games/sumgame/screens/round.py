"""Round screen: items, the market maker's quote, order entry, timer, risk check, log."""

from __future__ import annotations

import math
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from met_games.games.sumgame.engine import BUY, PASS, SELL, SumSession
from met_games.games.sumgame.screens.common import (
    SumScreen,
    crumb,
    event_banner,
    item_widget,
    log_text,
    round_text,
    top_bar,
)
from met_games.games.sumgame.ui import ui_for
from met_games.pause import GameKeyBar
from met_games.widgets import AMBER, BIG_ROWS, DIM, GREEN, RED, KeyButton, TitledPanel, big_lines

BAR_WIDTH = 26


def quote_text(bid: str, ask: str) -> Text:
    """Huge `BID @ ASK`: bid red ("you sell"), ask green ("you buy")."""
    b, a = big_lines(bid), big_lines(ask)
    bw, aw = max(len(b[0]), 8), max(len(a[0]), 7)
    out = Text()
    for i in range(BIG_ROWS):
        out.append(b[i].center(bw), style=f"bold {RED}")
        out.append("   @   " if i == BIG_ROWS // 2 else "       ", style="bold")
        out.append(a[i].center(aw), style=f"bold {GREEN}")
        out.append("\n")
    out.append("you sell".center(bw), style=RED)
    out.append("       ")
    out.append("you buy".center(aw), style=GREEN)
    return out


def market_title(session: SumSession) -> str:
    tick = session.config.TICK
    return "MARKET" if tick == 1 else f"MARKET · TICK {session.source.price(tick)}"


class RoundScreen(SumScreen):
    BINDINGS = [
        Binding("b", "buy", "buy"),
        Binding("s", "sell", "sell"),
        Binding("p", "pass_round", "pass"),
        Binding("left", "size(-1)", show=False),
        Binding("right", "size(1)", show=False),
        Binding("shift+left", "size(-5)", show=False),
        Binding("shift+right", "size(5)", show=False),
    ]

    DEFAULT_CSS = """
    RoundScreen #round-body { height: 1fr; }
    RoundScreen #round-left { width: 1fr; }
    RoundScreen #round-right { width: 36; }
    RoundScreen #cards { height: auto; margin-top: 1; }
    RoundScreen #timer { text-align: center; }
    RoundScreen #table-info { margin: 1 0 0 0; }
    RoundScreen #quote { width: 100%; margin-top: 1; text-align: center; }
    RoundScreen #tape { width: 100%; text-align: center; }
    RoundScreen #buttons { height: 1; margin: 1 0 0 0; }
    RoundScreen #log-panel { height: 1fr; }
    """

    def __init__(self, session: SumSession) -> None:
        super().__init__()
        self.session = session
        self.ui = ui_for(session)
        self.src = session.source
        self.rnd = session.current  # dealt by next_round_screen()
        self.order_size = 1
        self.done = False
        self.started = 0.0

    # ── layout ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        s, r = self.session, self.rnd
        yield top_bar(self.src, crumb(s), round_text(s, r), s.balance)
        if r.event:
            yield Static(event_banner(self.src, r.event), classes="event-banner")
        with Horizontal(id="round-body"):
            with Vertical(id="round-left"):
                with TitledPanel("TABLE", id="table"):
                    with Horizontal(id="cards"):
                        self.item_widgets = [item_widget(self.ui, r, i, i in r.face_up) for i in range(len(r.items))]
                        yield from self.item_widgets
                    yield Static(id="table-info", classes="dim")
                with TitledPanel(market_title(s), double=True, id="market"):
                    yield Static(id="quote")
                    yield Static(id="tape", classes="dim")
                with TitledPanel("ORDER", id="order"):
                    yield Static(id="size-line")
                    with Horizontal(id="buttons"):
                        yield KeyButton(id="buy", classes="buy")
                        yield KeyButton(id="sell", classes="sell")
                        yield KeyButton("[P] PASS", id="pass")
            with Vertical(id="round-right"):
                yield TitledPanel("TIMER", Static(id="timer"))
                yield TitledPanel("RISK CHECK", Static(id="risk"))
                yield TitledPanel("LOG", Static(id="log"), id="log-panel")
        keys = [("B", "buy @ ask"), ("S", "sell @ bid"), ("P", "pass")]
        if s.config.sizing == "choose":
            keys += [("←→", "size ±1"), ("shift+←→", "±5")]
        yield GameKeyBar(keys)

    def on_mount(self) -> None:
        self.started = self.clock()
        self.refresh_market()
        self.refresh_clock(0.0)
        self.ticker = self.set_interval(0.1, self.tick)

    # ── clock ───────────────────────────────────────────────────────────────

    def elapsed(self) -> float:
        return self.clock() - self.started

    def tick(self) -> None:
        if self.done:
            return
        t = self.elapsed()
        if t >= self.rnd.timer_s:
            self.session.timeout()
            self.finish()
            return
        if self.session.advance(t):
            self.on_flip()
        self.refresh_clock(t)

    def refresh_clock(self, t: float) -> None:
        total = self.rnd.timer_s
        remaining = max(0.0, total - t)
        secs = math.ceil(remaining)
        color = RED if remaining < 5 else AMBER
        out = Text()
        for line in big_lines(f"{secs // 60:02d}:{secs % 60:02d}"):
            out.append(line + "\n", style=f"bold {color}")
        filled = round(BAR_WIDTH * remaining / total)
        out.append("█" * filled, style=color)
        out.append("░" * (BAR_WIDTH - filled), style=DIM)
        self.query_one("#timer", Static).update(out)
        self.refresh_log(t)

    def refresh_log(self, t: float) -> None:
        text = log_text(self.session)
        r = self.rnd
        if r.flipped_at is not None:
            if text:
                text.append("\n")
            label = self.src.flip_label(r.items[r.flip_index])
            text.append(f"▲ {label} turned face up {max(0, int(t - r.flipped_at))}s ago", style=f"bold {AMBER}")
        if not text:
            text = Text("no trades yet", style=DIM)
        self.query_one("#log", Static).update(text)

    # ── market state ────────────────────────────────────────────────────────

    def on_flip(self) -> None:
        self.item_widgets[self.rnd.flip_index].show(face_up=True, fresh=True, tag="NEW")
        self.refresh_market()

    def sizes(self) -> tuple[int, int, int, int]:
        """(max_long, max_short, buy size, sell size) after clamping the chosen size to each side."""
        max_long, max_short = self.session.limits()
        if self.session.config.sizing == "fixed":
            return max_long, max_short, 1, 1
        self.order_size = max(1, min(self.order_size, max(max_long, max_short, 1)))
        return max_long, max_short, max(1, min(self.order_size, max_long)), max(1, min(self.order_size, max_short))

    def refresh_market(self) -> None:
        r, price = self.rnd, self.src.price
        m = r.market()
        up_sum = sum(r.values[i] for i in r.face_up)
        self.query_one("#table-info", Static).update(
            f"face up {up_sum} · hidden {len(r.hidden)} · settles between {m.settle_min} and {m.settle_max}"
        )
        self.query_one("#quote", Static).update(quote_text(price(r.bid), price(r.ask)))
        tape = self.query_one("#tape", Static)
        tape.display = self.session.config.mid_round_flip
        tape.update("tape  " + "  ·  ".join(f"{t:4.1f}s  {price(b)} @ {price(a)}" for t, b, a in r.tape[-2:]))
        self.refresh_order()

    def refresh_order(self) -> None:
        r, price = self.rnd, self.src.price
        m = r.market()
        max_long, max_short, buy_n, sell_n = self.sizes()
        if self.session.config.sizing == "choose":
            line = Text("size  ")
            line.append(f"◂ {self.order_size} ▸", style=f"bold {AMBER}")
            line.append(" units", style=DIM)
        else:
            line = Text("size  1 unit ", style="")
            line.append("(fixed)", style=DIM)
        self.query_one("#size-line", Static).update(line)

        buy, sell = self.query_one("#buy", KeyButton), self.query_one("#sell", KeyButton)
        ask, bid = price(r.ask), price(r.bid)
        buy.update(f"[B] BUY {buy_n} @ {ask}" if max_long >= 1 else f"[B] BUY @ {ask} — over budget")
        sell.update(f"[S] SELL {sell_n} @ {bid}" if max_short >= 1 else f"[S] SELL @ {bid} — over budget")
        buy.disabled, sell.disabled = max_long < 1, max_short < 1

        risk = Text()
        risk.append(f"max long  {max_long:>3}", style="bold")
        risk.append(f"   worst settle {m.settle_min}\n", style=DIM)
        risk.append(f"          loss/unit {self._loss(r.ask - m.settle_min)}\n", style=RED)
        risk.append(f"max short {max_short:>3}", style="bold")
        risk.append(f"   worst settle {m.settle_max}\n", style=DIM)
        risk.append(f"          loss/unit {self._loss(m.settle_max - r.bid)}", style=RED)
        self.query_one("#risk", Static).update(risk)

    def _loss(self, per_unit: Any) -> str:
        return "none (riskless)" if per_unit <= 0 else f"-${self.src.price(per_unit)}"

    # ── actions ─────────────────────────────────────────────────────────────

    def action_size(self, delta: int) -> None:
        if self.done or self.session.config.sizing != "choose":
            return
        self.order_size += delta
        self.refresh_order()

    def action_buy(self) -> None:
        self.decide(BUY)

    def action_sell(self) -> None:
        self.decide(SELL)

    def action_pass_round(self) -> None:
        self.decide(PASS)

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        self.decide({"buy": BUY, "sell": SELL, "pass": PASS}[message.button.id])

    def decide(self, action: str) -> None:
        if self.done:
            return
        t = self.elapsed()
        if t >= self.rnd.timer_s:
            self.tick()
            return
        if self.session.advance(t):  # new information just landed: show it, don't trade blind
            self.on_flip()
            return
        max_long, max_short, buy_n, sell_n = self.sizes()
        if (action == BUY and max_long < 1) or (action == SELL and max_short < 1):
            self.app.bell()
            return
        if action == BUY:
            self.session.buy(buy_n, t)
        elif action == SELL:
            self.session.sell(sell_n, t)
        else:
            self.session.pass_(t)
        self.finish()

    def finish(self) -> None:
        from met_games.games.sumgame.screens.reveal import RevealScreen

        self.done = True
        self.ticker.stop()
        self.app.switch_screen(RevealScreen(self.session))
