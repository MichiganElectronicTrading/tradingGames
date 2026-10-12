"""End of game: the final reveal and your trade-score report, then the results (owners included) and the tape."""

from __future__ import annotations

import csv
from pathlib import Path

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Static

from met_games import storage
from met_games.games.outcry.engine import OPEN_KIND, REPORT, RESULTS, TICK, YOU
from met_games.games.outcry.screens.common import OutcryScreen, big, clock_text, money, signed, top_bar
from met_games.games.outcry.stats import BUY, csv_rows, grouped, history_record, totals, your_trades
from met_games.games.sumgame.screens.common import start_session
from met_games.pause import GameKeyBar
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True)
    return t


def reveal_list(game) -> Text:
    """All values in reveal order, with LOWEST/HIGHEST labels, and settle = sum."""
    out = Text()
    values = []
    for i, r in enumerate(game.public().reveals):
        if i:
            out.append("  ")
        if r.label:
            out.append(f"{r.label} ", style=f"bold {AMBER}")
        out.append(str(r.value), style="bold")
        values.append(r.value)
    out.append("\n\nsettle = " + " + ".join(str(v) for v in values) + " = ", style=DIM)
    out.append(str(sum(values)), style=f"bold {AMBER}")
    return out


class FinalScreen(OutcryScreen):
    """The last number turns over; you score your own trades from your trade list (no scores shown)."""

    PHASES = (REPORT,)

    DEFAULT_CSS = """
    FinalScreen #last-value { height: 5; margin: 1 0; }
    FinalScreen #report-row { height: 1; margin-top: 1; }
    FinalScreen #report-hint { width: 1fr; padding-left: 2; }
    """

    def compose(self) -> ComposeResult:
        g = self.game
        yield top_bar(g, "FINAL")
        last = [r.value for r in g.public().reveals[g.config.rounds:]]
        what = "the last hidden number" if len(last) == 1 else "the last hidden numbers"
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield TitledPanel(
                    "FINAL REVEAL", Static(Text(f"{what} turns over — still anonymous", style=DIM)),
                    Static(big("  ".join(str(v) for v in last), f"bold {AMBER}"), id="last-value"),
                    Static(reveal_list(g)), double=True,
                )
                yield TitledPanel("YOUR TRADES", Static(self.trades_table()), Static(self.totals_text()))
            with Vertical(id="right"):
                with TitledPanel("SCORE YOUR TRADES", double=True):
                    with Horizontal(id="report-row"):
                        yield Input(type="integer", placeholder="score", id="report-input")
                        yield Static("net score, ⏎", id="report-hint", classes="dim")
                    yield Static(Text(
                        "each trade: +1 if it made money at the settle (bought below / sold above), −1 if it lost, "
                        "0 if it was at the settle — whatever its size. Enter the net (negatives allowed).", style=DIM))
                yield TitledPanel("TIMER", Static(id="timer", classes="timer"))
        yield GameKeyBar([("0-9 -", "type score"), ("⏎", "submit")])

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#report-input", Input).focus()

    def trades_table(self) -> Table | Text:
        rows = grouped(your_trades(self.game))
        if not rows:
            return Text("you made no trades", style=DIM)
        t = _table("ROUND", "WHEN", "SIDE", "PRICE", "LOTS", right=("PRICE", "LOTS"))
        for rnd, kind, side, price, lots, _, _ in rows:
            t.add_row(str(rnd), "open" if kind == OPEN_KIND else "outcry",
                      Text(side, style=f"bold {GREEN if side == BUY else RED}"), str(price), str(lots))
        return t

    def totals_text(self) -> Text:
        bought, sold = totals(your_trades(self.game))
        out = Text()
        out.append(f"bought {bought} · sold {sold} · final position ", style=DIM)
        out.append(signed(self.game.positions[YOU]), style=f"bold {AMBER}")
        return out

    def refresh_view(self) -> None:
        g = self.game
        self.query_one("#timer", Static).update(clock_text(g.seconds_left(), g.config.report_s))

    def on_input_submitted(self, message: Input.Submitted) -> None:
        text = message.value.strip()
        try:
            int(text)
        except ValueError:
            self.notify("enter a whole number, e.g. -3", severity="warning")
            return
        self.sync()
        if self.game.phase == REPORT:
            self.game.report(text)
        self.leave()


class TapeScreen(Screen):
    """T on the results: every trade of the game, with your fair when you were in it."""

    BINDINGS = [Binding("escape", "app.pop_screen", "back"), Binding("t", "app.pop_screen", "back", show=False)]

    DEFAULT_CSS = """
    TapeScreen #tape-scroll { height: 1fr; margin: 0 1; border: double #3FA7B5; border-title-color: #5FD4E0;
                              border-title-style: bold; padding: 0 1; }
    """

    def __init__(self, game) -> None:
        super().__init__()
        self.game = game

    def compose(self) -> ComposeResult:
        g = self.game
        yield TopBar(f"OUTCRY ▸ {g.mode}", f"FULL TAPE · SEED {g.seed}")
        t = _table("RND", "WHEN", "TIME", "BUYER", "SELLER", "PRICE", "AGGRESSOR", right=("PRICE", "TIME"))
        for tr in g.trades:
            start = g.rounds[tr.round - 1].outcry_start
            when = "open" if tr.kind == OPEN_KIND else "outcry"
            secs = "" if tr.kind == OPEN_KIND else f"{(tr.at - start) * TICK:.2f}s"
            mine = YOU in (tr.buyer, tr.seller)
            t.add_row(str(tr.round), when, secs, g.names[tr.buyer], g.names[tr.seller], str(tr.price),
                      g.names[tr.aggressor], style=f"bold {AMBER}" if mine else None)
        scroll = VerticalScroll(Static(t), id="tape-scroll")
        scroll.border_title = f"FULL TAPE · {len(g.trades)} TRADES · SETTLE {g.settle}"
        yield scroll
        yield KeyBar([("↑↓", "scroll"), ("Esc", "back")])


class ResultsScreen(OutcryScreen):
    PHASES = (RESULTS,)
    BINDINGS = [
        Binding("r", "replay", "replay seed"),
        Binding("t", "tape", "full tape"),
        Binding("e", "export", "export CSV"),
        Binding("l", "lobby", "lobby"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "lobby", "lobby", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    ResultsScreen #results-body { height: 1fr; padding: 0 1; }
    ResultsScreen .row { height: auto; }
    ResultsScreen .row TitledPanel { width: 1fr; }
    ResultsScreen .row > Vertical { height: auto; width: 1fr; }
    ResultsScreen #board { width: 2fr; }
    """

    def __init__(self, game) -> None:
        super().__init__(game)
        self.res = game.results()
        self.saved = False

    def compose(self) -> ComposeResult:
        g, res = self.game, self.res
        bar = top_bar(g, "RESULTS")
        bar.round_text = f"RESULTS · SEED {g.seed}"
        yield bar
        with VerticalScroll(id="results-body"):
            with Horizontal(classes="row"):
                yield TitledPanel("LEADERBOARD", Static(self.board()), Static(
                    Text("zero-sum: the eight P&Ls add up to $0", style=DIM)), double=True, id="board")
                with Vertical():
                    yield TitledPanel("YOUR REPORT", Static(self.report_text()))
                    yield TitledPanel("THE RANGE", Static(self.range_text()))
            with Horizontal(classes="row"):
                yield TitledPanel("YOUR EDGE", Static(self.edge_text()))
                yield TitledPanel("FORCED OPENS", Static(self.opens_text()))
                yield TitledPanel("OPENING WIDTH", Static(self.width_text()))
                yield TitledPanel("BEST / WORST TRADE", Static(self.best_worst_text()))
            yield TitledPanel("YOUR TRADES · SCORED", Static(self.scored_table()), Static(self.scored_summary()))
            yield TitledPanel("LAST TRADE PRICE BY ROUND", Static(self.prices_text()))
            yield TitledPanel("TRADER STYLES", Static(self.styles_text()))
        yield KeyBar([("R", "replay seed"), ("T", "full tape"), ("E", "export CSV"), ("L", "lobby"), ("Q", "quit")])

    def on_mount(self) -> None:
        super().on_mount()
        if not self.saved:
            storage.append_jsonl(self.ui.history_file, history_record(self.game))
            self.saved = True

    # ── panels ──────────────────────────────────────────────────────────────

    def board(self) -> Table:
        t = _table("RANK", "PLAYER", "NUMBER", "TRADES", "P&L", right=("NUMBER", "TRADES", "P&L"))
        for row in self.res.leaderboard:
            you = row.name == "YOU"
            t.add_row(str(row.rank), Text(row.name, style=f"bold {AMBER}" if you else "bold"), str(row.number),
                      str(row.trades), Text(money(row.pnl), style=f"bold {GREEN if row.pnl > 0 else RED if row.pnl < 0 else ''}"))
        return t

    def report_text(self) -> Text:
        res = self.res
        out = Text()
        if res.reported is None:
            out.append("✗ TIMED OUT", style=f"bold {RED}")
        elif res.report_correct:
            out.append(f"✓ CORRECT  {res.reported:+d}", style=f"bold {GREEN}")
        else:
            out.append(f"✗ you said {res.reported:+d}", style=f"bold {RED}")
        out.append(f"\nnet trade score {res.score:+d}", style="bold")
        if res.report_seconds is not None:
            out.append(f" · answered in {res.report_seconds:.1f}s", style=DIM)
        return out

    def scored_table(self) -> Table | Text:
        rows = grouped(self.res.your_trades)
        if not rows:
            return Text("you made no trades — net score 0", style=DIM)
        t = _table("ROUND", "WHEN", "SIDE", "PRICE", "TRADES", "SCORE", right=("PRICE", "TRADES", "SCORE"))
        for rnd, kind, side, price, _, trades, score in rows:
            each = f"{score:+d}" if score else "0"
            shown = each if trades == 1 else f"{each} ×{trades}"
            t.add_row(str(rnd), "open" if kind == OPEN_KIND else "outcry",
                      Text(side, style=f"bold {GREEN if side == BUY else RED}"), str(price), str(trades),
                      Text(shown, style=f"bold {GREEN if score > 0 else RED if score < 0 else DIM}"))
        return t

    def scored_summary(self) -> Text:
        scores = [y.score for y in self.res.your_trades]
        out = Text()
        out.append(f"made money {scores.count(1)} · lost {scores.count(-1)} · at the settle {scores.count(0)}"
                   f" · settle {self.res.settle} → net ", style=DIM)
        out.append(f"{self.res.score:+d}", style=f"bold {AMBER}")
        return out

    def range_text(self) -> Text:
        lo, hi = self.res.true_range
        slo, shi = self.res.range_seen
        out = Text()
        out.append("true range          ", style=DIM)
        out.append(f"{lo}–{hi}", style=f"bold {AMBER}")
        out.append("\nrange you could see ", style=DIM)
        out.append(f"{slo}–{shi}", style="bold")
        out.append(f"\nsettle {self.res.settle}", style=DIM)
        return out

    def edge_text(self) -> Text:
        res = self.res
        if not res.your_trades:
            return Text("no trades — no edge", style=DIM)
        out = Text()
        out.append(f"{len(res.your_trades)} trades\n", style=DIM)
        out.append("vs settle      ", style=DIM)
        out.append(f"{money(res.avg_edge_settle, 2)}/trade", style=f"bold {GREEN if res.avg_edge_settle >= 0 else RED}")
        out.append("\nvs YOUR fair   ", style=DIM)
        out.append(f"{money(res.avg_edge_fair, 2)}/trade", style=f"bold {GREEN if res.avg_edge_fair >= 0 else RED}")
        out.append("\n(your fair when you traded — the skill metric)", style=DIM)
        return out

    def opens_text(self) -> Text:
        res = self.res
        out = Text()
        out.append("you responded: ", style=DIM)
        out.append(f"traded {res.responses_traded} · passed {res.responses_passed}", style="bold")
        out.append("\nyou opened: ", style=DIM)
        out.append(f"{res.opens}×, {res.open_fills} fills", style="bold")
        return out

    def width_text(self) -> Text:
        res = self.res
        out = Text()
        out.append("yours      ", style=DIM)
        out.append("—" if res.your_open_width is None else f"{res.your_open_width:.1f}", style=f"bold {AMBER}")
        out.append("\ncomputers  ", style=DIM)
        out.append("—" if res.computer_open_width is None else f"{res.computer_open_width:.1f}", style="bold")
        out.append("\naverage ask − bid on forced opens", style=DIM)
        return out

    def best_worst_text(self) -> Text:
        res = self.res
        if res.best is None:
            return Text("no trades", style=DIM)
        out = Text()
        for label, y in (("best ", res.best), ("worst", res.worst)):
            if out:
                out.append("\n")
            t = y.trade
            out.append(f"{label} R{t.round} {y.side} @ {t.price} ", style="bold")
            out.append(money(y.edge_settle), style=f"bold {GREEN if y.edge_settle >= 0 else RED}")
            out.append(f" ({'open' if t.kind == OPEN_KIND else 'outcry'}, {y.counterparty})", style=DIM)
        return out

    def prices_text(self) -> Text:
        out = Text()
        for i, (rnd, price) in enumerate(self.res.last_prices):
            if i:
                out.append(" ▸ ", style=DIM)
            out.append(f"R{rnd} ", style=DIM)
            out.append("—" if price is None else str(price), style="bold")
        out.append(" ▸ settle ", style=DIM)
        out.append(str(self.res.settle), style=f"bold {AMBER}")
        return out

    def styles_text(self) -> Text:
        out = Text()
        for i, row in enumerate(r for r in self.res.leaderboard if r.style):
            if i:
                out.append(" · ", style=DIM)
            out.append(f"{row.name} ", style="bold")
            out.append(row.style, style=AMBER)
        return out

    # ── keys ────────────────────────────────────────────────────────────────

    def action_replay(self) -> None:
        g = self.game
        start_session(self.app, g.config.replace(seed=g.seed), g.mode, switch=True)

    def action_tape(self) -> None:
        self.app.push_screen(TapeScreen(self.game))

    def action_export(self) -> None:
        path = Path.cwd() / f"{self.game.source.key}_session_{self.game.seed}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(csv_rows(self.game))
        self.notify(f"exported {path}")

    def action_lobby(self) -> None:
        self.app.pop_screen()

