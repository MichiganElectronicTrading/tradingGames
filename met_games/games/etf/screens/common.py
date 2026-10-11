"""Shared pieces of the ETF Arb screens: top bar, clock bridge, basket table, timer."""

from __future__ import annotations

from decimal import Decimal
from time import monotonic

from rich import box
from rich.table import Table
from rich.text import Text
from textual.screen import Screen

from met_games.games.etf.engine import TICK, YOU, EtfGame
from met_games.games.etf.model import REBAL, SPLIT, RoundPlan, fmt_px, fmt_weight, wxp
from met_games.games.etf.stats import money
from met_games.games.sumgame.ui import ui_for
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, TopBar, big_lines

EVENT_ROW = f"bold {AMBER}"


class EtfTopBar(TopBar):
    """`ETF ARB ▸ MODE · ROUND r / n · P&L ±$x`."""

    def __init__(self, crumb: str, round_text: str, right: str) -> None:
        super().__init__(crumb, round_text)
        self.right = right

    def render(self) -> Table:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=2, no_wrap=True)
        grid.add_column(justify="center", ratio=1, no_wrap=True)
        grid.add_column(justify="right", ratio=2, no_wrap=True)
        grid.add_row(f" {self.crumb}", self.round_text, f"{self.right} ")
        return grid


def top_bar(game: EtfGame, center: str | None = None) -> EtfTopBar:
    text = center or f"ROUND {game.round.number} / {game.config.rounds}"
    return EtfTopBar(f"ETF ARB ▸ {game.mode}", text, f"P&L {money(game.total(YOU))}")


def basket_table(game: EtfGame, plan: RoundPlan, solved: bool = False) -> Table:
    """BASKET: TICKER, WEIGHT, PRICE, CHG, %, Δ W × P, W × P (at the price tick, every difficulty), then NAV · Σ.
    CHG is the stock's price move; Δ W × P is how much its W × P moved, so last NAV + Σ Δ W × P = Σ W × P. Event rows are
    amber with ⚑; CHG reads "split"/"rebal". During the round the weights — and the ⚑ row's W × P, marked
    amber — are the table's stale ones (the event is NOT applied) and the sum is "?". `solved` shows the
    adjusted weights, strikes the stale W × P through next to the correct one, and fills in Σ = NAV."""
    places = game.config.price_places
    tick = plan.tick
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for col in ("TICKER", "WEIGHT", "PRICE", "CHG", "%", "Δ W × P", "W × P"):
        t.add_column(col, justify="left" if col == "TICKER" else "right", no_wrap=True)
    event = plan.event
    weights = plan.weights if solved else plan.shown_weights
    for i, ticker in enumerate(plan.tickers):
        p, prev, w = plan.prices[i], plan.prev_prices[i], weights[i]
        flagged = event is not None and event.ticker == ticker
        if flagged:
            chg, pct = event.chg_label, "—"
        else:
            diff = p - prev
            chg = f"{diff:+.{places}f}" if diff else f"{0:.{places}f}"
            pct = f"{diff / prev * 100:+.2f}%" if diff else "0.00%"
        cell = Text(fmt_px(wxp(w, p, tick), tick))
        if flagged:
            stale = fmt_px(wxp(plan.shown_weights[i], p, tick), tick)
            cell = Text(stale, style=f"bold {AMBER}")
            if solved:  # the stale value struck through, then the correct one (separate spans, not a base style)
                cell = Text()
                cell.append(stale, style=f"strike {DIM}")
                cell.append(f" {fmt_px(wxp(w, p, tick), tick)}", style=f"bold {AMBER}")
        delta = Text(signed(plan.wxp_change(i), tick))
        if flagged:
            delta = Text(signed(plan.wxp_change(i), tick), style=f"bold {AMBER}")  # from the stale weight, like W × P
            if solved:
                delta = Text()
                delta.append(signed(plan.wxp_change(i), tick), style=f"strike {DIM}")
                delta.append(f" {signed(plan.wxp_change(i, adjusted=True), tick)}", style=f"bold {AMBER}")
        weight = fmt_weight(w)
        if solved and flagged:
            how = {SPLIT: f"×{event.ratio}", REBAL: "new"}.get(event.kind, f"÷{event.ratio}")
            weight = f"{weight} ({fmt_weight(event.old_weight)} {how})"
        t.add_row(("⚑ " if flagged else "") + ticker, weight, f"{p:.{places}f}", chg, pct, delta, cell,
                  style=EVENT_ROW if flagged else None)
    total = Text(f"Σ = {fmt_px(plan.nav, tick)}", style=f"bold {AMBER}") if solved else Text("Σ = ?", style="bold")
    t.add_row(Text("NAV", style="bold"), "", "", "", "", "", total, end_section=False)
    return t


def signed(x: Decimal, tick: Decimal) -> str:
    """+4 / −0.3 / 0 at the tick's precision."""
    text = fmt_px(abs(x), tick)
    return text if x == 0 else ("+" if x > 0 else "-") + text


def last_nav_title(game: EtfGame, plan: RoundPlan, title: str) -> str:
    """Panel title carrying the NAV you start from: last round's (or the opening NAV before round 1)."""
    label = "opening NAV" if plan.number == 1 else "last NAV"
    return f"{title} · {label} {fmt_px(game.market.nav_before(plan.number), plan.tick)}"


def clock_text(seconds: float, total: float) -> Text:
    secs = int(-(-seconds // 1))
    color = RED if seconds < 3 else AMBER
    out = Text()
    for i, line in enumerate(big_lines(f"{secs // 60:02d}:{secs % 60:02d}")):
        out.append(("\n" if i else "") + line, style=f"bold {color}")
    width = 24
    filled = round(width * seconds / total) if total else 0
    out.append("\n" + "█" * filled, style=color)
    out.append("░" * (width - filled), style=DIM)
    return out


def big(text: str, style: str) -> Text:
    out = Text()
    for i, line in enumerate(big_lines(text)):
        out.append(("\n" if i else "") + line, style=style)
    return out


def signed_money(x: Decimal) -> Text:
    return Text(money(x), style=f"bold {GREEN if x > 0 else RED if x < 0 else ''}")


class EtfScreen(Screen):
    """Base: bridges real (or injected) time to the game's tick clock; moves on when the phase changes."""

    PHASES: tuple[str, ...] = ()

    DEFAULT_CSS = """
    EtfScreen #body { height: 1fr; }
    EtfScreen #left { width: 1fr; }
    EtfScreen #right { width: 44; }
    EtfScreen .timer { text-align: center; }
    EtfScreen .event-banner { height: auto; }
    """

    def __init__(self, game: EtfGame) -> None:
        super().__init__()
        self.game = game
        self.ui = ui_for(game.config)
        self.leaving = False
        self.t0 = 0.0
        self.tick0 = 0

    def clock(self) -> float:
        """Seconds from `app.etf_clock` if set (tests inject a fake), else monotonic."""
        return getattr(self.app, "etf_clock", monotonic)()

    def on_mount(self) -> None:
        self.t0, self.tick0 = self.clock(), self.game.now
        self.refresh_view()
        self.ticker = self.set_interval(0.1, self.sync)

    def sync(self) -> None:
        if self.leaving:
            return
        self.game.advance_to(self.tick0 + int((self.clock() - self.t0) / TICK + 1e-9))
        if self.game.phase not in self.PHASES:
            self.leave()
            return
        self.refresh_view()

    def leave(self) -> None:
        from met_games.games.etf.screens import screen_for

        self.leaving = True
        self.ticker.stop()
        self.app.switch_screen(screen_for(self.game))

    def refresh_view(self) -> None:
        """Redraw from the game state (subclasses)."""
