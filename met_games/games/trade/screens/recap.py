"""Trading Game recap: final standings, making/taking/balance/reports tiles, the hands table,
mistakes and bankroll; history + CSV export like the sum games."""

from __future__ import annotations

import csv
from pathlib import Path

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
from met_games.games.sumgame.screens.common import start_session
from met_games.games.sumgame.screens.recap import NEG_ROW
from met_games.games.sumgame.stats import money
from met_games.games.sumgame.ui import ui_for
from met_games.games.trade.engine import YOU, TradeSession
from met_games.games.trade.screens.common import CIRCLED, crumb
from met_games.games.trade.stats import (
    bankroll,
    csv_rows,
    history_record,
    market_label,
    mistakes,
    session_stats,
    settled,
    standings,
)
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar, fmt_balance


def _signed(x: int) -> Text:
    return Text(money(x), style=f"bold {GREEN if x > 0 else RED if x < 0 else ''}")


def standings_table(session: TradeSession) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for col in ("RANK", "PLAYER", "TOTAL P&L"):
        t.add_column(col, justify="right" if col == "TOTAL P&L" else "left", no_wrap=True)
    for rank, who, total in standings(session):
        t.add_row(str(rank), Text(who, style=f"bold {AMBER}" if who == YOU else "bold"), _signed(total))
    return t


def hands_table(session: TradeSession) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for col in ("HAND", "SEAT", "YOUR MKT", "FILLS b/a", "MAKE", "TAKE", "TOTAL", "RANK", "REPORT"):
        t.add_column(col, justify="left" if col in ("YOUR MKT", "REPORT") else "right", no_wrap=True)
    hands = settled(session)
    for i, h in enumerate(hands):
        mine = h.your_turn()
        if h.reported is None:
            report = Text("—", style=DIM)
        elif h.report_correct:
            report = Text(f"✓ {h.reported}", style=GREEN)
        else:
            report = Text(f"✗ {h.reported} ({h.pnl(YOU)})", style=RED)
        total = h.pnl(YOU)
        t.add_row(
            str(h.number), CIRCLED[h.seat_of(YOU)], market_label(mine),
            f"{mine.bid_filled}/{mine.ask_filled}" if mine.posted else "—",
            _signed(h.making_pnl), _signed(h.taking_pnl), _signed(total), f"{h.ranks()[YOU]}/4", report,
            style=NEG_ROW if total < 0 else None, end_section=i == len(hands) - 1,
        )
    st = session_stats(session)
    t.add_row(
        "TOTAL", "", "", "", _signed(st.making), _signed(st.taking), _signed(st.making + st.taking), "",
        f"{st.reports_correct}/{st.reports_total}", style="bold",
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

    def __init__(self, session: TradeSession) -> None:
        super().__init__()
        self.session = session
        self.ui = ui_for(session.config)
        self.saved = False

    def compose(self) -> ComposeResult:
        s = self.session
        st = session_stats(s)
        yield TopBar(crumb(s), f"RECAP · SEED {s.seed}", s.balance)
        with VerticalScroll(id="recap-body"):
            yield TitledPanel("FINAL STANDINGS", Static(standings_table(s)), double=True)
            with Horizontal(id="stat-row"):
                making = _signed(st.making)
                making.append("\nfills on your markets", style=DIM)
                yield TitledPanel("MAKING", Static(making))
                taking = _signed(st.taking)
                taking.append(f"\nedge vs table fair {money(st.edge_taken, 2)}", style=DIM)
                yield TitledPanel("TAKING", Static(taking))
                bal = Text(fmt_balance(st.final_balance), style=f"bold {AMBER}")
                bal.append(f"\n{money(st.change)} session", style=GREEN if st.change >= 0 else RED)
                yield TitledPanel("BALANCE", Static(bal), double=True)
                reports = Text(f"{st.reports_correct}/{st.reports_total} correct", style="bold")
                avg = "—" if st.avg_answer_s is None else f"{st.avg_answer_s:.1f}s"
                reports.append(f"\navg answer {avg}", style=DIM)
                yield TitledPanel("REPORTS", Static(reports))
            yield TitledPanel("HANDS", Static(hands_table(s)), double=True)
            with Horizontal(id="bottom-row"):
                errs = mistakes(s)
                body = Text("\n".join(f"• {m}" for m in errs)) if errs else Text("none — clean session ✓", style=GREEN)
                yield TitledPanel("MISTAKES", Static(body), id="mistakes")
                path = Text(" ▸ ".join(str(b) for b in bankroll(s)), style="bold")
                yield TitledPanel("BANKROLL", Static(path), id="bankroll")
        yield KeyBar([
            ("R", "replay seed"), ("N", "next difficulty"), ("E", "export CSV"), ("L", "lobby"), ("Q", "quit"),
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
