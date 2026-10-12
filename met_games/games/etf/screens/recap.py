"""ETF Arb recap: leaderboard, tiles, the rounds table, mistakes; history + CSV export."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from met_games import storage
from met_games.games.etf.engine import RECAP, TICK, TIMEOUT, YOU
from met_games.games.etf.model import SKIP, fmt_px
from met_games.games.etf.screens.common import EtfScreen, signed_money, top_bar
from met_games.games.etf.stats import csv_rows, history_record, leaderboard, mistakes, right_way, tiles
from met_games.games.sumgame.config import NEXT_MODE
from met_games.games.sumgame.screens.common import start_session
from met_games.games.sumgame.screens.recap import NEG_ROW
from met_games.widgets import AMBER, DIM, GREEN, TITLE, KeyBar, TitledPanel


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True)
    return t


class RecapScreen(EtfScreen):
    PHASES = (RECAP,)
    BINDINGS = [
        Binding("r", "replay", "replay seed"),
        Binding("n", "next_mode", "next difficulty"),
        Binding("e", "export", "export CSV"),
        Binding("l", "lobby", "lobby"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "lobby", "lobby", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    RecapScreen #recap-body { height: 1fr; padding: 0 1; }
    RecapScreen #tiles { height: auto; }
    RecapScreen #tiles TitledPanel { width: 1fr; height: 5; }
    """

    def __init__(self, game) -> None:
        super().__init__(game)
        self.saved = False

    def compose(self) -> ComposeResult:
        g = self.game
        tl = tiles(g)
        yield top_bar(g, f"RECAP · SEED {g.seed}")
        with VerticalScroll(id="recap-body"):
            yield TitledPanel("LEADERBOARD", Static(self.board()), double=True)
            with Horizontal(id="tiles"):
                yield TitledPanel("RIGHT DIRECTION", Static(self.tile(f"{tl.right_trades} / {tl.trades}",
                                                                      "right-way trades")))
                yield TitledPanel("RIGHT SKIPS", Static(self.tile(f"{tl.right_skips} / {tl.skip_rounds}",
                                                                  "skips on skip rounds")))
                yield TitledPanel("FIRST TO TRADE", Static(self.tile(f"{tl.first}", "rounds you were first")))
                avg = "—" if tl.avg_decision is None else f"{tl.avg_decision:.1f}s"
                yield TitledPanel("AVG DECISION", Static(self.tile(avg, "trades and skips")))
            yield TitledPanel("ROUNDS", Static(self.rounds_table()), double=True)
            errs = mistakes(g)
            body = Text("\n".join(f"• {m}" for m in errs)) if errs else Text("none — clean session ✓", style=GREEN)
            yield TitledPanel("MISTAKES", Static(body))
        yield KeyBar([("R", "replay seed"), ("N", "next difficulty"), ("E", "export CSV"), ("L", "lobby"),
                      ("Q", "quit")])

    def on_mount(self) -> None:
        super().on_mount()
        if not self.saved:
            storage.append_jsonl(self.ui.history_file, history_record(self.game))
            self.saved = True

    @staticmethod
    def tile(big_text: str, small: str) -> Text:
        out = Text(big_text, style=f"bold {AMBER}")
        out.append(f"\n{small}", style=DIM)
        return out

    def board(self) -> Table:
        t = _table("RANK", "PLAYER", "TOTAL NET", right=("TOTAL NET",))
        for rank, name, total in leaderboard(self.game):
            t.add_row(str(rank), Text(name, style=f"bold {AMBER}" if name == "YOU" else "bold"), signed_money(total))
        return t

    def rounds_table(self) -> Table:
        g = self.game
        t = _table("RND", "NAV", "QUOTE", "RIGHT CALL", "YOU", "TIME", "NET", right=("NAV", "TIME", "NET"))
        done = [r for r in g.rounds if r.end is not None]
        for i, r in enumerate(done):
            call, edge = g.right_call(r)
            d = r.decisions[YOU]
            f = d.fill
            if f:
                you = f"{f.side} {f.units}" + (" ★" if f.first else "")
            else:
                you = "TIMEOUT" if d.action == TIMEOUT else "SKIP"
            k = r.plan.tick
            gap = ("+" if edge >= 0 else "-") + fmt_px(abs(edge), k)
            right = f"{call} {gap}" if call != SKIP else f"SKIP ({gap})"
            when = "—" if d.t is None or d.action == TIMEOUT else f"{d.t * TICK:.1f}s"
            event = " ⚑" if r.plan.event else ""
            t.add_row(f"{r.number}{event}", fmt_px(r.nav, k), f"{fmt_px(r.plan.bid, k)} @ {fmt_px(r.plan.ask, k)}", right,
                      you, when,
                      signed_money(d.net), style=NEG_ROW if f and not right_way(f) else None,
                      end_section=i == len(done) - 1)
        t.add_row("TOTAL", "", "", "", "", "", signed_money(sum((r.decisions[YOU].net for r in done), Decimal(0))),
                  style="bold")
        return t

    def action_replay(self) -> None:
        g = self.game
        start_session(self.app, g.config.replace(seed=g.seed), g.mode, switch=True)

    def action_next_mode(self) -> None:
        mode = NEXT_MODE.get(self.game.mode, "EASY")
        start_session(self.app, self.game.source.presets[mode], mode, switch=True)

    def action_export(self) -> None:
        path = Path.cwd() / f"{self.game.source.key}_session_{self.game.seed}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(csv_rows(self.game))
        self.notify(f"exported {path}")

    def action_lobby(self) -> None:
        self.app.pop_screen()
