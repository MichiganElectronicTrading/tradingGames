"""End of game (bust or deck done), the bet review, and the high-score tables."""

from __future__ import annotations

import math

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from met_games import storage
from met_games.games.hilo.config import DECK_LABELS, DECKS
from met_games.games.hilo.engine import OVER
from met_games.games.hilo.model import pct
from met_games.games.hilo.scores import (
    GRADES,
    HISTORY_FILE,
    history_record,
    record,
    review_rows,
    summary,
    top,
)
from met_games.games.hilo.screens.common import HiloScreen, big, top_bar
from met_games.games.sumgame.screens.common import start_session
from met_games.widgets import AMBER, DIM, GREEN, RED, TITLE, KeyBar, TitledPanel, TopBar

SCORE_MODES = ("EASY", "MEDIUM", "HARD", "CUSTOM")


def _table(*cols: str, right: tuple[str, ...] = ()) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {TITLE}", border_style=DIM, expand=True, pad_edge=False)
    for c in cols:
        t.add_column(c, justify="right" if c in right else "left", no_wrap=True)
    return t


def scores_table(deck: str, mode: str, n: int, timed: bool = False) -> Table | Text:
    entries = top(deck, mode, n, timed)
    if not entries:
        return Text("no scores yet", style=DIM)
    t = _table("#", "SCORE", "MULTIPLE", "DATE", "SEED", right=("SCORE", "MULTIPLE"))
    for i, e in enumerate(entries, start=1):
        t.add_row(str(i), f"{e['score']:,}", f"×{e['multiple']:.2f}", e["date"], str(e["seed"]),
                  style=f"bold {AMBER}" if i == 1 else None)
    return t


class EndScreen(HiloScreen):
    PHASES = (OVER,)
    BINDINGS = [
        Binding("r", "replay", "replay deck"),
        Binding("n", "new_deck", "new deck"),
        Binding("b", "review", "review bets"),
        Binding("l", "lobby", "lobby"),
        Binding("q", "app.quit", "quit"),
        Binding("escape", "lobby", "lobby", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    EndScreen #end-body { height: 1fr; padding: 0 1; }
    EndScreen #cols { height: auto; }
    EndScreen #end-left, EndScreen #end-right { width: 1fr; height: auto; }
    EndScreen #final { height: 6; }
    """

    def __init__(self, game) -> None:
        super().__init__(game)
        self.rank = record(game)
        storage.append_jsonl(HISTORY_FILE, history_record(game))
        self.sum = summary(game)

    def compose(self) -> ComposeResult:
        g = self.game
        yield top_bar(g, "BUST — GAME OVER" if g.bust else "DECK DONE")
        if self.rank == 1:
            yield Static("★ NEW HIGH SCORE ★", classes="event-banner", id="new-high")
        with VerticalScroll(id="end-body"):
            with Horizontal(id="cols"):
                with Vertical(id="end-left"):
                    yield TitledPanel("FINAL SCORE", Static(self.final_text(), id="final"), double=True)
                    yield TitledPanel("GRADES", Static(self.grades_table()), Static(self.speed_text()))
                with Vertical(id="end-right"):
                    yield TitledPanel("CAPITAL", Static(self.capital_text()))
                    yield TitledPanel("WORST BET", Static(self.worst_text()))
                    label = f"HIGH SCORES · {DECK_LABELS[g.config.deck]} · {g.mode}"
                    label += " · TIMED" if g.config.timed else ""
                    yield TitledPanel(label, Static(scores_table(g.config.deck, g.mode, 5, g.config.timed)))
            deck = "" if g.config.deck == "interview" and g.mode == "EASY" else f" --deck {g.config.deck}"
            yield Static(Text(f"club play: everyone runs  met-games hilo --seed {g.seed}{deck}  for this deck order",
                              style=DIM), id="club")
        yield KeyBar([("R", "replay deck"), ("N", "new deck"), ("B", "review bets"), ("L", "lobby"), ("Q", "quit")])

    def final_text(self) -> Text:
        g = self.game
        out = big(f"{g.score:,}".replace(",", ""), f"bold {AMBER}")
        out.append(f"\nbets {g.bet_points:,} + capital bonus {g.bonus:,}", style="bold")
        if g.bust:
            out.append("   BUST — bonus forfeited", style=f"bold {RED}")
        if self.rank:
            out.append(f"   #{self.rank} on this board", style=GREEN)
        return out

    def grades_table(self) -> Table:
        n = max(1, len(self.game.bets))
        t = _table("GRADE", "COUNT", "%", right=("COUNT", "%"))
        for grade in GRADES:
            c = self.sum.grades[grade]
            t.add_row(grade, str(c), f"{100 * c / n:.0f}%")
        return t

    def speed_text(self) -> Text:
        s = self.sum
        out = Text()
        if self.game.config.timed:
            out.append(f"LIGHTNING {s.lightning} · FAST {s.fast}\n", style="bold")
        out.append(f"best combo ×{float(s.best_combo):g} · best streak {s.best_streak}", style=DIM)
        return out

    def capital_text(self) -> Text:
        g = self.game
        out = Text()
        out.append(f"{g.start:,} → {g.capital:,}  ", style="bold")
        out.append(f"×{float(g.multiple):.2f}", style=f"bold {GREEN if g.multiple >= 1 else RED}")
        out.append(f"\nKelly benchmark ×{float(self.sum.benchmark):.2f}", style=AMBER)
        out.append(" (staking exactly k every bet on this deck order)", style=DIM)
        if g.bust:
            out.append("\nbonus: none — you busted", style=RED)
        elif g.capital > g.start:
            out.append(f"\nbonus = round(1000 × log2({g.capital:,} ÷ {g.start:,})) = "
                       f"round({1000 * math.log2(g.capital / g.start):.1f}) = {g.bonus:,}", style=DIM)
        else:
            out.append("\nbonus: none — finished at or below the start", style=DIM)
        return out

    def worst_text(self) -> Text:
        b = self.sum.worst
        if b is None:
            return Text("no bets", style=DIM)
        o = b.odds
        prev = "" if b.showing is None else f"{b.showing} → "
        right = f"{o.right} {pct(o.k)}%" if o.right else "sit out (no edge)"
        yours = "timeout" if b.timeout else ("sit out" if b.percent == 0 else f"{b.side} {b.percent}%")
        out = Text(f"#{b.number}  {prev}{b.next}", style="bold")
        out.append(f"\nh {o.h} · same {o.same} · l {o.l}", style=DIM)
        out.append(f"\nright {right} · yours {yours} · {b.grade}", style="bold")
        ideal = "a PERFECT" if o.k > 0 else "a DISCIPLINE sit-out"
        out.append(f"\n{self.sum.worst_lost:,} points short of {ideal}", style=RED)
        return out

    def action_replay(self) -> None:
        g = self.game
        start_session(self.app, g.config.replace(seed=g.seed), g.mode, switch=True)

    def action_new_deck(self) -> None:
        g = self.game
        start_session(self.app, g.config.replace(seed=None), g.mode, switch=True)

    def action_review(self) -> None:
        self.app.push_screen(ReviewScreen(self.game))

    def action_lobby(self) -> None:
        self.app.pop_screen()


class ReviewScreen(Screen):
    """B on the end screen: every bet, the right bet next to yours."""

    BINDINGS = [Binding("escape", "app.pop_screen", "back"), Binding("b", "app.pop_screen", "back", show=False)]

    DEFAULT_CSS = """
    ReviewScreen #review-scroll { height: 1fr; margin: 0 1; border: double #3FA7B5; border-title-color: #5FD4E0;
                                  border-title-style: bold; padding: 0 1; }
    """

    def __init__(self, game) -> None:
        super().__init__()
        self.game = game

    def compose(self) -> ComposeResult:
        g = self.game
        yield TopBar(f"HI/LO ▸ {g.mode}", f"REVIEW · SEED {g.seed}")
        t = _table("#", "SHOWING", "H/SAME/L", "RIGHT", "YOURS", "GRADE", "MULTIPLIERS", "POINTS", "CAPITAL",
                   right=("POINTS", "CAPITAL"))
        for row in review_rows(g):
            t.add_row(*row, style=f"{RED}" if row[5] == "MISS" else None)
        scroll = VerticalScroll(Static(t), id="review-scroll")
        scroll.border_title = f"REVIEW BETS · {len(g.bets)} bets · score {g.score:,}"
        yield scroll
        yield KeyBar([("↑↓", "scroll"), ("Esc", "back")])


class HighScoresScreen(Screen):
    """Top 10 per deck and difficulty, as tabs (←→). T switches between the untimed and timed tables."""

    BINDINGS = [
        Binding("left", "tab(-1)", "previous"),
        Binding("right", "tab(1)", "next"),
        Binding("t", "toggle_timed", "untimed / timed"),
        Binding("escape", "app.pop_screen", "back"),
    ]

    DEFAULT_CSS = """
    HighScoresScreen #scores-body { padding: 1 2; }
    """

    def __init__(self, deck: str, mode: str, timed: bool = False) -> None:
        super().__init__()
        self.timed = timed
        self.tabs = [(d, m) for d in DECKS for m in SCORE_MODES]
        self.index = self.tabs.index((deck, mode)) if (deck, mode) in self.tabs else 0

    def compose(self) -> ComposeResult:
        yield TopBar("MET GAMES ▸ HI/LO ▸ HIGH SCORES")
        with Vertical(id="scores-body"):
            yield Static(id="tabs")
            yield TitledPanel("TOP 10", Static(id="table"), double=True, id="scores-panel")
        yield KeyBar([("←→", "deck / difficulty"), ("T", "untimed / timed"), ("Esc", "back")])

    def on_mount(self) -> None:
        self.refresh_tab()

    def refresh_tab(self) -> None:
        deck, mode = self.tabs[self.index]
        tabs = Text()
        for d in DECKS:
            tabs.append(f" {DECK_LABELS[d]} ", style="bold" if d == deck else DIM)
            for m in SCORE_MODES:
                tabs.append(f" {m} ", style=f"bold #000000 on {AMBER}" if (d, m) == (deck, mode) else DIM)
            tabs.append("   ")
        timing = "TIMED" if self.timed else "UNTIMED"
        self.query_one("#tabs", Static).update(tabs)
        self.query_one("#scores-panel").border_title = f"TOP 10 · {DECK_LABELS[deck]} · {mode} · {timing}"
        self.query_one("#table", Static).update(scores_table(deck, mode, 10, self.timed))

    def action_toggle_timed(self) -> None:
        self.timed = not self.timed
        self.refresh_tab()

    def action_tab(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.tabs)
        self.refresh_tab()
