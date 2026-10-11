"""The bet screen: score strip, card, cards left, your bet, the stake guide (or the clock, when timed), last
bets — and the reveal flash."""

from __future__ import annotations

from fractions import Fraction

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from met_games.games.hilo.config import MINIMAL, ODDS
from met_games.games.hilo.engine import BET, OVER, REVEAL, Bet
from met_games.games.hilo.model import (
    BLACK,
    COMBO_CAP,
    HIGHER,
    LABELS,
    LOWER,
    RED,
    combo_multiplier,
    pct,
    snap_stake,
    stake_amount,
)
from met_games.games.hilo.scores import multipliers
from met_games.games.hilo.screens.common import HiloScreen, HiloTopBar, big, card_art, top_bar
from met_games.widgets import AMBER, DIM, GREEN, RED as RED_COLOR, SELECTED, TITLE, KeyBar, TitledPanel

FLASH_S = 0.6
BAR = 30
GRADE_STYLE = {"PERFECT": GREEN, "GOOD": GREEN, "DISCIPLINE": GREEN, "OK": AMBER, "SAT OUT": DIM, "MISS": RED_COLOR}
ARROWS = {HIGHER: "▲", LOWER: "▼", RED: "♥", BLACK: "♠"}


def side_text(bet: Bet) -> str:
    if bet.timeout:
        return "timeout"
    return "sit out" if bet.percent == 0 else f"{bet.side} {bet.percent}%"


def grade_line(bet: Bet) -> Text:
    out = Text()
    out.append(bet.grade, style=f"bold {GRADE_STYLE[bet.grade]}")
    mult = multipliers(bet)
    if mult:
        out.append(f" · {mult}", style=AMBER)
    out.append(f" → {bet.points:+d}", style="bold")
    return out


class BetScreen(HiloScreen):
    PHASES = (BET, REVEAL)
    BINDINGS = [
        Binding("h", "side('HIGHER')", show=False),
        Binding("l", "side('LOWER')", show=False),
        Binding("r", "side('RED')", show=False),
        Binding("b", "side('BLACK')", show=False),
        # ↑ / ↓: HIGHER / LOWER (RED / BLACK on red/black). Priority, so no focused widget can take the arrows.
        Binding("up", "pick(0)", show=False, priority=True),
        Binding("down", "pick(1)", show=False, priority=True),
        *[Binding(str(d), f"stake({d * 10})", show=False) for d in range(10)],
        Binding("a", "stake(100)", show=False),
        Binding("left", "nudge(-5)", show=False),
        Binding("right", "nudge(5)", show=False),
        Binding("shift+left", "snap(-1)", show=False),
        Binding("shift+right", "snap(1)", show=False),
        Binding("left_square_bracket", "snap(-1)", show=False),  # for terminals without Shift+arrows
        Binding("right_square_bracket", "snap(1)", show=False),
        Binding("enter", "lock", "lock"),
    ]

    DEFAULT_CSS = """
    BetScreen #strip { height: 2; padding: 0 1; background: #1C232C; }
    BetScreen #body { height: 1fr; }
    BetScreen #left { width: 1fr; }
    BetScreen #right { width: 44; }
    BetScreen #top-row { height: auto; }
    BetScreen #card-panel { width: 15; }
    BetScreen #board-panel { width: 1fr; }
    BetScreen #clock { text-align: center; }
    BetScreen #guide { height: auto; }
    BetScreen #flash-panel { border: double #F2C14E; }
    """

    def __init__(self, game) -> None:
        super().__init__(game)
        self.side: str | None = None
        self.percent = 0
        self.flash_until: float | None = None

    def compose(self) -> ComposeResult:
        yield top_bar(self.game)
        yield Static(id="strip")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                with Horizontal(id="top-row"):
                    yield TitledPanel("CARD", Static(id="card"), id="card-panel")
                    yield TitledPanel("CARDS LEFT", Static(id="board"), id="board-panel")
                yield TitledPanel("YOUR BET", Static(id="bet"), double=True, id="bet-panel")
                yield TitledPanel("REVEAL", Static(id="flash"), id="flash-panel")
            with Vertical(id="right"):
                if self.game.config.timed:
                    yield TitledPanel("CLOCK", Static(id="clock"))
                else:
                    yield TitledPanel("STAKE GUIDE", Static(id="guide"))
                yield TitledPanel("LAST BETS", Static(id="last"))
        up, down = self.game.sides
        keys = f"{up[0]}/{down[0]} ↑↓"
        yield KeyBar([(keys, "side"), ("←→", "±5%"), ("⇧←→ / [ ]", "±25%"), ("0–9 · A", "all-in"), ("⏎", "lock")])

    # ── clock + flash ───────────────────────────────────────────────────────

    def sync(self) -> None:
        if self.leaving:
            return
        g = self.game
        g.advance_to(self.target_tick())
        if g.phase == REVEAL:
            if self.flash_until is None:  # a timeout landed: flash it too
                self.flash_until = self.clock() + FLASH_S
            elif self.clock() >= self.flash_until:
                self.end_flash()
                return
        elif g.phase == OVER:
            self.leave()
            return
        self.refresh_view()

    def end_flash(self) -> None:
        g = self.game
        g.next_bet()
        self.flash_until = None
        self.side, self.percent = None, 0
        if g.phase == OVER:
            self.leave()
            return
        self.refresh_view()

    # ── view ────────────────────────────────────────────────────────────────

    def refresh_view(self) -> None:
        g = self.game
        bar = self.query_one(HiloTopBar)
        bar.round_text = f"BET {min(g.number, g.total_bets)} / {g.total_bets}"
        bar.right = f"CAPITAL {g.capital:,}"
        bar.refresh()
        self.query_one("#strip", Static).update(self.strip_text())
        self.query_one("#card", Static).update(card_art(g.showing, face_down=g.redblack))
        self.query_one("#board", Static).update(self.board_text())
        self.query_one("#bet", Static).update(self.bet_text())
        if g.config.timed:
            self.query_one("#clock", Static).update(self.clock_text())
        else:
            self.query_one("#guide", Static).update(self.guide_text())
        self.query_one("#last", Static).update(self.last_text())
        flashing = g.phase == REVEAL and g.bets
        self.query_one("#flash-panel").display = bool(flashing)
        if flashing:
            self.query_one("#flash", Static).update(self.flash_text(g.bets[-1]))

    def strip_text(self) -> Text:
        g = self.game
        combo = combo_multiplier(g.streak)
        out = Text()
        out.append("SCORE ", style=DIM)
        out.append(f"{g.bet_points:,}", style=f"bold {AMBER}")
        out.append("   COMBO ", style=DIM)
        out.append(f"×{float(combo):g}", style=f"bold {RED_COLOR if combo >= 2 else AMBER}")
        out.append(f" · streak {g.streak} ", style=DIM)
        filled = round(10 * (combo - 1) / (COMBO_CAP - 1))
        out.append("█" * filled + "░" * (10 - filled), style=RED_COLOR if combo >= 2 else AMBER)
        if combo >= 2:
            out.append("  ON FIRE", style=f"bold {RED_COLOR}")
        out.append("\nlast: ", style=DIM)
        if g.bets:
            out.append_text(grade_line(g.bets[-1]))
        else:
            out.append("—", style=DIM)
        return out

    def board_text(self) -> Text:
        g = self.game
        o = g.odds()
        board = g.config.board
        out = Text()
        if board == MINIMAL:
            out.append("cards left ", style=DIM)
            out.append(str(len(g.left)), style=f"bold {AMBER}")
            seen = g.cards[: g.pos]
            if g.redblack:
                seen = [b.next for b in g.bets]
            out.append("\nlast three  ", style=DIM)
            out.append(" ".join(str(c) for c in seen[-3:]) or "—", style="bold")
            return out
        if g.redblack:
            out.append("reds ", style=DIM)
            out.append(str(o.h), style=f"bold {RED_COLOR}")
            out.append(" · blacks ", style=DIM)
            out.append(str(o.l), style="bold")
        else:
            show = g.showing.rank
            for r in range(1, 14):
                out.append(f"{LABELS.get(r, str(r)):>3}", style=f"bold {TITLE if r < show else AMBER if r > show else ''}")
            out.append("\n")
            for r in range(1, 14):
                n = sum(1 for c in g.left if c.rank == r)
                out.append(f"{n:>3}", style=TITLE if r < show else AMBER if r > show else DIM)
            out.append("\nlower ", style=DIM)
            out.append(str(o.l), style=f"bold {TITLE}")
            out.append(" · same ", style=DIM)
            out.append(str(o.same), style="bold")
            out.append(" · higher ", style=DIM)
            out.append(str(o.h), style=f"bold {AMBER}")
        if board == ODDS and o.total:
            up, down = ("P red", "P black") if g.redblack else ("P higher", "P lower")
            out.append(f"\n{up} {pct(Fraction(o.h, o.total))}% · {down} {pct(Fraction(o.l, o.total))}%", style=GREEN)
        return out

    def bet_text(self) -> Text:
        g = self.game
        out = Text()
        up, down = g.sides
        for i, side in enumerate((up, down)):
            if i:
                out.append("     ")
            label = f" [{side[0]}] {side} {ARROWS[side]} "
            out.append(label, style=SELECTED if self.side == side else "bold")
        out.append("\n\n")
        out.append_text(big(f"{self.percent}", f"bold {AMBER}"))
        out.append(f"   %  = {stake_amount(g.capital, self.percent):,} of {g.capital:,}", style="bold")
        filled = round(BAR * self.percent / 100)
        out.append("\n" + "█" * filled, style=AMBER)
        out.append("░" * (BAR - filled), style=DIM)
        out.append("\n0       25      50      75   all-in", style=DIM)
        if g.phase == BET:
            hint = "pick a side, then a stake" if self.side is None else (
                "stake key locks it (quick lock)" if g.config.quick_lock else "⏎ to lock")
            out.append(f"\n{hint}", style=DIM)
        return out

    def clock_text(self) -> Text:
        g = self.game
        total = g.config.time_s
        left = g.seconds_left() if g.phase == BET else float(total)
        used = 1 - left / total
        color = RED_COLOR if left < total / 4 else AMBER
        out = big(f"{left:.1f}", f"bold {color}")
        out.append("\n")
        for i in range(BAR):
            f = i / BAR
            zone = AMBER if f < 0.25 else GREEN if f < 0.5 else DIM
            out.append("█" if f >= used else "░", style=zone)
        out.append("\nLIGHTNING FAST    normal", style=DIM)
        elapsed = total - left
        if elapsed <= total / 4:
            tier, rest = "LIGHTNING ×2", total / 4 - elapsed
        elif elapsed <= total / 2:
            tier, rest = "FAST ×1.5", total / 2 - elapsed
        else:
            tier, rest = "normal ×1", left
        out.append(f"\n{tier} · {rest:.1f}s left in tier", style=f"bold {color}")
        return out

    def guide_text(self) -> Text:
        """Untimed bets: the key map and the current combo, in place of the clock."""
        up, down = self.game.sides
        out = Text()
        for key, what in ((f"{up[0]}/{down[0]} ↑↓", f"{up} / {down}"), ("0–9", "stake 0–90%"), ("A", "all-in"),
                          ("← →", "±5%"), ("⇧← ⇧→", "previous / next 25%"), ("[ ]", "same as ⇧← ⇧→"),
                          ("⏎", "lock · skip the reveal")):
            out.append(f"{key:<8}", style=f"bold {AMBER}")
            out.append(f"{what}\n", style=DIM)
        g = self.game
        combo = combo_multiplier(g.streak)
        out.append("\nCOMBO ", style=DIM)
        out.append(f"×{float(combo):g}", style=f"bold {RED_COLOR if combo >= 2 else AMBER}")
        out.append(f" · streak {g.streak}", style=DIM)
        return out

    def last_text(self) -> Text:
        g = self.game
        if not g.bets:
            return Text("no bets yet", style=DIM)
        out = Text()
        for b in g.bets[-4:][::-1]:
            prev = "" if b.showing is None else f"{b.showing} → "
            out.append(f"{prev}{b.next}  ", style="bold")
            out.append(f"{side_text(b):<13}", style=DIM)
            out.append(f"{b.points:+d}\n", style=f"bold {GRADE_STYLE[b.grade]}")
        latest = g.bets[-1]
        o = latest.odds
        right = f"right was {o.right} {pct(o.k)}%" if o.right else "no edge — sitting out was right"
        out.append(f"{right} · {latest.grade}", style=DIM)
        return out

    def flash_text(self, bet: Bet) -> Text:
        out = card_art(bet.next)
        out.append("\n")
        if bet.percent == 0:
            out.append("timed out — " if bet.timeout else "sat out — ", style=DIM)
            out.append("no change", style="bold")
        elif bet.result > 0:
            out.append(f"✓ {bet.side}  +{bet.amount:,}", style=f"bold {GREEN}")
        elif bet.result < 0:
            out.append(f"✗ {bet.side}  −{bet.amount:,}", style=f"bold {RED_COLOR}")
        else:
            out.append("= same rank — stake returned", style="bold")
        out.append(f"   capital {bet.capital_after:,}\n", style=DIM)
        out.append_text(grade_line(bet))
        if self.game.bust:
            out.append("\nBUST — game over", style=f"bold {RED_COLOR}")
        out.append("\n⏎ skip", style=DIM)
        return out

    # ── input ───────────────────────────────────────────────────────────────

    def action_pick(self, index: int) -> None:
        """↑ picks the first side (HIGHER / RED), ↓ the second (LOWER / BLACK)."""
        self.action_side(self.game.sides[index])

    def action_side(self, side: str) -> None:
        if self.game.phase == BET and side in self.game.sides:
            self.side = side
            self.refresh_view()

    def action_stake(self, percent: int) -> None:
        if self.game.phase != BET:
            return
        self.percent = percent
        if self.side is not None and self.game.config.quick_lock:
            self.action_lock()
        else:
            self.refresh_view()

    def action_nudge(self, delta: int) -> None:
        if self.game.phase == BET:
            self.percent = max(0, min(100, self.percent + delta))
            self.refresh_view()

    def action_snap(self, step: int) -> None:
        """Shift+← / Shift+→ (or [ / ]): the previous / next multiple of 25%. Never locks."""
        if self.game.phase == BET:
            self.percent = snap_stake(self.percent, step)
            self.refresh_view()

    def action_lock(self) -> None:
        g = self.game
        if self.leaving:
            return
        if g.phase == REVEAL:  # ⏎ skips the flash
            self.end_flash()
            return
        self.sync()
        if self.leaving or g.phase != BET:
            return
        if self.percent > 0 and self.side is None:
            self.app.bell()
            self.notify("pick a side first", severity="warning")
            return
        g.lock(self.side if self.percent else None, self.percent)
        self.flash_until = self.clock() + FLASH_S
        self.refresh_view()

