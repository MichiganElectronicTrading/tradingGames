"""The round screen: basket, ETF quote, your order, the timer, and the race."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from mtt_games.games.etf.engine import NAMES, OPEN, TICK, YOU, ticks
from mtt_games.games.etf.model import BUY, SELL, fmt_px
from mtt_games.games.etf.screens.common import (
    EtfScreen,
    basket_table,
    big,
    clock_text,
    last_nav_title,
    signed_money,
    top_bar,
)
from mtt_games.widgets import AMBER, DIM, GREEN, RED, KeyBar, KeyButton, TitledPanel

BLOCKS = 5


class RoundScreen(EtfScreen):
    PHASES = (OPEN,)
    BINDINGS = [
        Binding("b", "trade('BUY')", "buy"),
        Binding("s", "trade('SELL')", "sell"),
        Binding("k", "skip", "skip"),
        Binding("left", "units(-1)", show=False),
        Binding("right", "units(1)", show=False),
        Binding("shift+left", "units(-5)", show=False),
        Binding("shift+right", "units(5)", show=False),
        Binding("enter", "skip_ahead", "skip ahead"),
        Binding("escape", "quit_game", "quit"),
    ]

    DEFAULT_CSS = """
    RoundScreen #quote { height: auto; }
    RoundScreen .side { width: 1fr; height: auto; content-align: center middle; text-align: center; }
    RoundScreen #buttons { height: 1; margin-top: 1; }
    RoundScreen #buttons KeyButton { margin-right: 1; }
    """

    def __init__(self, game) -> None:
        super().__init__(game)
        self.units = game.config.max_units

    def compose(self) -> ComposeResult:
        g = self.game
        event = g.round.plan.event
        yield top_bar(g)
        if event:
            yield Static(event.banner, classes="event-banner", id="event-banner")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel(last_nav_title(g, g.round.plan, "BASKET"), Static(basket_table(g, g.round.plan),
                                                                                   id="basket"))
                with TitledPanel("ETF QUOTE", double=True, id="quote-panel"):
                    with Horizontal(id="quote"):
                        yield Static(id="bid", classes="side")
                        yield Static(id="ask", classes="side")
                with TitledPanel("ORDER", id="order"):
                    yield Static(id="units-line")
                    yield Static(id="hint", classes="dim")
                    with Horizontal(id="buttons"):
                        yield KeyButton(id="buy", classes="buy")
                        yield KeyButton(id="sell", classes="sell")
                        yield KeyButton("[K] SKIP", id="skip")
            with Vertical(id="right"):
                yield TitledPanel("TIMER", Static(id="timer", classes="timer"))
                yield TitledPanel("THE RACE · FIRST TRADE +20%", Static(id="race"))
                yield TitledPanel("SESSION", Static(id="session"))
        yield KeyBar([("B", "buy"), ("S", "sell"), ("K", "skip"), ("←→", "units ±1"), ("⇧←→", "±5"),
                      ("Esc", "quit")])

    # ── view ────────────────────────────────────────────────────────────────

    def acted(self) -> bool:
        return YOU in self.game.round.decisions

    def sizes(self) -> tuple[int, int]:
        r = self.game.round
        return min(self.units, r.ask_left), min(self.units, r.bid_left)

    def refresh_view(self) -> None:
        g = self.game
        r, plan = g.round, g.round.plan
        bid = big(fmt_px(plan.bid, plan.tick).replace(",", ""), f"bold {RED}")
        bid.append(f"\nBID · you sell · {r.bid_left} left", style=RED)
        ask = big(fmt_px(plan.ask, plan.tick).replace(",", ""), f"bold {GREEN}")
        ask.append(f"\nASK · you buy · {r.ask_left} left", style=GREEN)
        self.query_one("#bid", Static).update(bid)
        self.query_one("#ask", Static).update(ask)

        line = Text("units  ")
        line.append(f"◂ {self.units} ▸", style=f"bold {AMBER}")
        self.query_one("#units-line", Static).update(line)
        self.query_one("#hint", Static).update(
            f"fee ${g.config.fee:g} · at {self.units} units you need a gap over ${g.config.fee / self.units:.2f}")
        buy_n, sell_n = self.sizes()
        buy, sell, skip = (self.query_one(f"#{i}", KeyButton) for i in ("buy", "sell", "skip"))
        buy.update(f"[B] BUY {buy_n} @ {fmt_px(plan.ask, plan.tick)}" if r.ask_left else "[B] BUY — none left")
        sell.update(f"[S] SELL {sell_n} @ {fmt_px(plan.bid, plan.tick)}" if r.bid_left else "[S] SELL — none left")
        buy.disabled = self.acted() or not r.ask_left
        sell.disabled = self.acted() or not r.bid_left
        skip.disabled = self.acted()

        self.query_one("#timer", Static).update(clock_text(g.seconds_left(), g.config.timer_s))
        self.query_one("#race", Static).update(self.race_text())
        self.query_one("#session", Static).update(self.session_text())

    def race_text(self) -> Text:
        g = self.game
        r = g.round
        out = Text()
        for seat, trader in g.traders.items():
            out.append(f"{NAMES[seat]:<8}", style="bold")
            d = r.decisions.get(seat)
            if d and d.fill:
                out.append(f"{d.fill.side} {d.fill.units} · +{d.t * TICK:.1f}s", style=GREEN if d.fill.side == BUY else RED)
            elif d:
                out.append("skipped", style=DIM)
            else:
                due = max(1, trader.decide_at(r.number))
                done = min(BLOCKS, round(BLOCKS * g.t / due))
                out.append("pricing ", style=DIM)
                out.append("▮" * done + "▯" * (BLOCKS - done), style=AMBER)
            out.append("\n")
        mine = r.decisions.get(YOU)
        out.append(f"{'YOU':<8}", style=f"bold {AMBER}")
        if mine and mine.fill:
            out.append(f"{mine.fill.side} {mine.fill.units} · +{mine.t * TICK:.1f}s", style="bold")
        elif mine:
            out.append("skipped", style=DIM)
        else:
            out.append("your move", style=DIM)
        out.append("\n\n")
        first = r.first
        if first is None:
            out.append("bonus still open", style=f"bold {GREEN}")
        else:
            out.append(f"bonus taken · {NAMES[first.who]}", style=DIM)
        return out

    def session_text(self) -> Text:
        g = self.game
        done = [r for r in g.rounds if r.end is not None]
        if not done:
            return Text("first round", style=DIM)
        out = Text()
        for r in done:
            out.append(f"R{r.number:<3}", style=DIM)
            out.append_text(signed_money(r.decisions[YOU].net))
            out.append("\n")
        out.append("total ", style=DIM)
        out.append_text(signed_money(g.total(YOU)))
        return out

    # ── actions ─────────────────────────────────────────────────────────────

    def action_units(self, delta: int) -> None:
        self.units = max(1, min(self.game.config.max_units, self.units + delta))
        self.refresh_view()

    def on_key_button_pressed(self, message: KeyButton.Pressed) -> None:
        if message.button.id == "skip":
            self.action_skip()
        else:
            self.action_trade(BUY if message.button.id == "buy" else SELL)

    def action_trade(self, side: str) -> None:
        if self.leaving:
            return
        self.sync()
        g = self.game
        if self.leaving or self.acted() or not g.can_trade(YOU, side):
            self.app.bell()
            return
        buy_n, sell_n = self.sizes()
        g.trade(YOU, side, buy_n if side == BUY else sell_n)
        self.after_act()

    def action_skip(self) -> None:
        if self.leaving:
            return
        self.sync()
        if self.leaving or self.acted():
            return
        self.game.skip()
        self.after_act()

    def after_act(self) -> None:
        if self.game.phase != OPEN:
            self.leave()
            return
        self.query_one(KeyBar).set_keys([("⏎", "skip ahead"), ("Esc", "quit")])
        self.refresh_view()

    def action_skip_ahead(self) -> None:
        """Once you've acted, jump to the bell instead of watching the rest of the race."""
        g = self.game
        if self.leaving or not self.acted():
            return
        g.advance_to(g.round.start + ticks(g.config.timer_s))
        self.leave()

    def action_quit_game(self) -> None:
        self.leaving = True
        self.ticker.stop()
        self.app.pop_screen()

