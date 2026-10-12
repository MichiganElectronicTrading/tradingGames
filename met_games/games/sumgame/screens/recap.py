"""Session recap: stat panels, rounds table, mistakes, bankroll path; history + CSV export."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games import storage
from met_games.games.sumgame.config import NEXT_MODE
from met_games.games.sumgame.engine import OUT_OF_RISK, SumSession
from met_games.games.sumgame.screens.common import crumb, start_session, top_bar
from met_games.games.sumgame.stats import (
    bankroll,
    csv_rows,
    history_record,
    mistakes,
    money,
    played,
    session_stats,
    trade_label,
)
from met_games.games.sumgame.ui import ui_for
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, fmt_balance

NEG_ROW = "on #3A1218"


def _signed(x: Any, text: str) -> Text:
    return Text(text, style=f"bold {GREEN if x > 0 else RED if x < 0 else ''}")


def end_banner(session: SumSession) -> str:
    reason = session.end_reason
    if reason == OUT_OF_RISK:
        bal = fmt_balance(session.balance, session.source.places)
        reason += f" — {bal} can't cover a 1-unit worst case on either side of the next quote"
    return f"■ SESSION ENDED EARLY · {reason}"


def rounds_table(session: SumSession) -> Table:
    price, places = session.source.price, session.source.places
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for col in ("RND", "QUOTE", "FAIR", "TRADE", "EDGE/U", "EDGE $", "SETTLE", "P&L", "REPORT", "DECIDE"):
        t.add_column(col, justify="left" if col in ("TRADE", "REPORT") else "right", no_wrap=True)
    rounds = played(session)
    for i, r in enumerate(rounds):
        d = r.decision
        if r.reported is None:
            report = Text("—", style=DIM)
        elif r.report_correct:
            report = Text(f"✓ {price(r.reported)}", style=GREEN)
        else:
            report = Text(f"✗ {price(r.reported)} ({price(r.pnl)})", style=RED)
        t.add_row(
            str(r.number),
            f"{price(d.bid)} @ {price(d.ask)}",
            f"{d.fair:.2f}",
            trade_label(r),
            "—" if d.edge_per_unit is None else f"{d.edge_per_unit:+.2f}",
            money(d.edge_dollars, 2) if d.is_trade else "—",
            str(r.settle),
            _signed(r.pnl, money(r.pnl, places)),
            report,
            f"{d.t:.1f}s",
            style=NEG_ROW if d.is_trade and d.edge_per_unit < 0 else None,
            end_section=i == len(rounds) - 1,
        )
    s = session_stats(session)
    trades = sum(1 for r in rounds if r.decision.is_trade)
    avg_decide = sum(r.decision.t for r in rounds) / len(rounds) if rounds else 0.0
    t.add_row(
        "TOTAL", "", "", f"{trades} trade{'s' * (trades != 1)}", "", money(s.edge_taken, 2), "",
        _signed(s.realized, money(s.realized, places)), f"{s.reports_correct}/{s.reports_total}",
        f"{avg_decide:.1f}s", style="bold",
    )
    return t


class RecapScreen(Screen):
    BINDINGS = [
        Binding("r", "replay", "replay same seed"),
        Binding("n", "next_mode", "next difficulty"),
        Binding("e", "export", "export CSV"),
        Binding("l", "lobby", "lobby"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "lobby", "lobby", show=False),
    ]

    DEFAULT_CSS = """
    RecapScreen #recap-body { height: 1fr; padding: 0 1; }
    RecapScreen #stat-row { height: auto; }
    RecapScreen #stat-row TitledPanel { width: 1fr; height: 5; }
    RecapScreen #bottom-row { height: auto; }
    RecapScreen #mistakes { width: 2fr; }
    RecapScreen #bankroll { width: 1fr; }
    """

    def __init__(self, session: SumSession) -> None:
        super().__init__()
        self.session = session
        self.ui = ui_for(session)
        self.saved = False

    def compose(self) -> ComposeResult:
        s = self.session
        places = s.source.places
        st = session_stats(s)
        yield top_bar(s.source, crumb(s), f"RECAP · SEED {s.seed}", s.balance)
        if s.end_reason:
            yield Static(end_banner(s), classes="event-banner", id="end-reason")
        with VerticalScroll(id="recap-body"):
            with Horizontal(id="stat-row"):
                final = Text(fmt_balance(st.final_balance, places), style=f"bold {AMBER}")
                final.append(f"\n{money(st.change, places)} session", style=GREEN if st.change >= 0 else RED)
                yield TitledPanel("FINAL BALANCE", Static(final), double=True)
                edge = _signed(st.edge_taken, money(st.edge_taken, 2))
                edge.append("\nexpected $ of your trades", style=DIM)
                yield TitledPanel("EDGE TAKEN", Static(edge))
                luck = _signed(st.luck, money(st.luck, 2))
                luck.append("\nrealized − edge", style=DIM)
                yield TitledPanel("LUCK", Static(luck))
                reports = Text(f"{st.reports_correct}/{st.reports_total} correct", style="bold")
                avg = "—" if st.avg_answer_s is None else f"{st.avg_answer_s:.1f}s"
                reports.append(f"\navg answer {avg}", style=DIM)
                yield TitledPanel("P&L REPORTS", Static(reports))
            yield TitledPanel("ROUNDS", Static(rounds_table(s)), double=True)
            with Horizontal(id="bottom-row"):
                errs = mistakes(s)
                body = Text("\n".join(f"• {m}" for m in errs)) if errs else Text("none — clean session ✓", style=GREEN)
                yield TitledPanel("MISTAKES", Static(body), id="mistakes")
                path = Text(" ▸ ".join(s.source.price(b) for b in bankroll(s)), style="bold")
                yield TitledPanel("BANKROLL", Static(path), id="bankroll")
        yield KeyBar([
            ("R", "replay same seed"), ("N", "next difficulty"), ("E", "export CSV"), ("L", "lobby"), ("Q", "quit"),
        ])

    def on_mount(self) -> None:
        if not self.saved:
            storage.append_jsonl(self.ui.history_file, history_record(self.session))
            self.saved = True

    def action_replay(self) -> None:
        s = self.session
        start_session(self.app, s.config.replace(seed=s.seed), s.mode, switch=True)

    def action_next_mode(self) -> None:
        mode = NEXT_MODE.get(self.session.mode, "EASY")
        start_session(self.app, self.session.source.presets[mode], mode, switch=True)

    def action_export(self) -> None:
        path = Path.cwd() / f"{self.session.source.key}_session_{self.session.seed}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(csv_rows(self.session))
        self.notify(f"exported {path}")

    def action_lobby(self) -> None:
        self.app.pop_screen()
