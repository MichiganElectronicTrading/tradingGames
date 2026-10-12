"""After each round: the solved NAV, the gap and the right call, your trade's math, and the race log."""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from met_games.games.etf.engine import NAMES, RESULT, TICK, TIMEOUT, YOU
from met_games.games.etf.model import BUY, SKIP, fmt_px
from met_games.games.etf.screens.common import EtfScreen, basket_table, last_nav_title, signed_money, top_bar
from met_games.games.etf.stats import missed_at_max, money, right_way, size_story
from met_games.pause import GameKeyBar
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, TitledPanel


def signed_px(x, tick) -> str:
    return ("+" if x >= 0 else "-") + fmt_px(abs(x), tick)


class ResultScreen(EtfScreen):
    PHASES = (RESULT,)
    BINDINGS = [Binding("enter", "next", "next round")]

    def compose(self) -> ComposeResult:
        g = self.game
        r = g.round
        yield top_bar(g, f"ROUND {r.number} / {g.config.rounds} · RESULT")
        if r.plan.event:
            yield Static(r.plan.event.banner, classes="event-banner")
        with VerticalScroll(id="body"):
            yield TitledPanel(last_nav_title(g, r.plan, "NAV"), Static(basket_table(g, r.plan, solved=True)),
                              Static(self.event_note()),
                              double=True)
            with Horizontal(id="cols"):
                with Vertical(id="left"):
                    yield TitledPanel("THE GAP", Static(self.gap_text()))
                    yield TitledPanel("SIZE AT THE BID / ASK", Static(self.size_text()))
                with Vertical(id="right"):
                    yield TitledPanel("YOUR TRADE", Static(self.trade_text()), double=True)
                    yield TitledPanel("RACE LOG", Static(self.race_log()))
        last = len(g.rounds) >= g.config.rounds
        yield GameKeyBar([("⏎", "recap" if last else "next round")])

    DEFAULT_CSS = """
    ResultScreen #cols { height: auto; }
    ResultScreen #left, ResultScreen #right { height: auto; }
    ResultScreen #right { width: 1fr; }
    """

    def event_note(self) -> Text:
        e = self.game.round.plan.event
        if e is None:
            return Text()
        return Text(f"⚑ {e.ticker}: NAV uses the adjusted weight; the table showed the old one", style=AMBER)

    def gap_text(self) -> Text:
        g = self.game
        r, p = g.round, g.round.plan
        call, edge = g.right_call(r)
        u = g.right_units(r)
        out = Text()
        k = p.tick
        out.append(f"quote {fmt_px(p.bid, k)} @ {fmt_px(p.ask, k)} · NAV {fmt_px(r.nav, k)}\n", style="bold")
        out.append(f"NAV − ask = {signed_px(r.nav - p.ask, k)}   bid − NAV = {signed_px(p.bid - r.nav, k)}\n", style=DIM)
        out.append("right call  ", style=DIM)
        style = f"bold {GREEN if call == BUY else RED if call != SKIP else AMBER}"
        if call == SKIP:
            out.append(f"SKIP — best gap {signed_px(edge, k)} × {u} = ${edge * u:.2f} doesn't beat the ${g.config.fee:g} fee",
                       style=style)
        else:
            out.append(f"{call} — gap {fmt_px(edge, k)} × {u} = ${edge * u:.2f} > ${g.config.fee:g} fee", style=style)
        mine = r.decisions[YOU].fill
        n = mine.units if mine else u
        out.append(f"\nbreak-even gap at {n} units: ${g.config.fee / n:.2f}", style=DIM)
        return out

    def trade_text(self) -> Text:
        g = self.game
        r = g.round
        d = r.decisions[YOU]
        out = Text()
        if d.fill is None:
            out.append("timed out — counted as a skip" if d.action == TIMEOUT else "skipped", style="bold")
            call, _ = g.right_call(r)
            if call == SKIP:
                out.append("\nthe right call was SKIP ✓", style=GREEN)
            else:
                out.append(f"\nthe right call, {call} {g.right_units(r)}, would have made "
                           f"{money(missed_at_max(g, r))}", style=RED)
            return out
        f = d.fill
        k = r.plan.tick
        nav, price = fmt_px(r.nav, k), fmt_px(f.price, k)
        formula = f"({nav} − {price})" if f.side == BUY else f"({price} − {nav})"
        out.append(f"{f.side} {f.units} @ {price} · +{d.t * TICK:.1f}s\n", style="bold")
        out.append("gross  ", style=DIM)
        out.append(f"{formula} × {f.units} = {money(f.gross)}\n")
        out.append("fee    ", style=DIM)
        out.append(f"{money(-f.fee)}\n")
        out.append("bonus  ", style=DIM)
        if f.bonus:
            out.append(f"{money(f.bonus)}  ({g.config.bonus * 100:g}% of {money(f.gross - f.fee)} — first trade)\n",
                       style=GREEN)
        elif f.first:
            out.append("none — first trade, but gross − fee wasn't positive\n", style=DIM)
        else:
            out.append(f"none — {NAMES[r.first.who]} traded first\n", style=DIM)
        out.append("net    ", style=DIM)
        out.append_text(signed_money(f.net))
        return out

    def race_log(self) -> Table:
        g = self.game
        r = g.round
        t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
        for col in ("WHO", "TIME", "TRADE", "", "NET"):
            t.add_column(col, justify="right" if col in ("TIME", "NET") else "left", no_wrap=col != "TRADE")
        order = sorted(r.decisions.values(), key=lambda d: (d.t is None, d.t or 0, d.who))
        for d in order:
            who = Text(NAMES[d.who], style=f"bold {AMBER}" if d.who == YOU else "bold")
            when = "—" if d.t is None else f"+{d.t * TICK:.1f}s"
            if d.fill:
                f = d.fill
                trade = f"{f.side} {f.units}" + (" ★" if f.first else "")
                mark = Text("✓ right way", style=GREEN) if right_way(f) else Text("✗ wrong way", style=RED)
                t.add_row(who, when, trade, mark, signed_money(f.net))
            else:
                note = d.note or ("timed out" if d.action == TIMEOUT else "")
                t.add_row(who, when, "SKIP", Text(note, style=DIM), Text("—", style=DIM))
        return t

    def size_text(self) -> Text:
        g = self.game
        out = Text(size_story(g, g.round, BUY))
        out.append("\n" + size_story(g, g.round, "SELL"))
        return out

    def action_next(self) -> None:
        if not self.leaving:
            self.game.next_round()
            self.leave()
