"""Outcry engine: setup, the tick clock, and the round flow. Pure Python, no Textual.

Eight players (you + the computer traders) each hold one hidden number; one contract settles at the
sum of all of them. Each of the rounds is: forced open → forced response → timed open outcry →
an anonymous reveal. After the last round the remaining number(s) turn over, you report your P&L,
and the results (owners included) are shown.

Time is a counter of 0.25 s ticks (`now`). Nothing reads a wall clock: the UI moves the clock forward
with `advance_to()`, and tests drive whole games instantly with `advance()`.

Randomness: one `random.Random(seed)` draws the whole setup (range, numbers, styles, openers,
response orders, reveal schedule); each computer trader then gets its own RNG seeded from it.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from met_games.games.outcry.book import BID, OFFER, Book, Result
from met_games.games.outcry.commands import (
    BID_CMD,
    BOTH,
    CANCEL_ALL,
    CANCEL_BID,
    CANCEL_OFFER,
    HIT,
    LIFT,
    OFFER_CMD,
    CommandError,
    parse_command,
)
from met_games.games.outcry.config import PRESETS, OutcryConfig
from met_games.games.outcry.model import FairView, Knowledge, SeenReveal, Universe, draw_setup, fair_view, knowledge_of
from met_games.games.outcry.traders import BUY, PASS, SELL, Trader, make_trader

TICK = 0.25
OPEN, RESPOND, OUTCRY, CLOSED, REPORT, RESULTS = "open", "respond", "outcry", "closed", "report", "results"
TIMEOUT = "timeout"
YOU = 0
OPEN_KIND, OUTCRY_KIND = "open", "outcry"
AUTO_HALF_WIDTH = 5  # your timed-out open is auto-quoted mid ± 5


def ticks(seconds: float) -> int:
    return round(seconds / TICK)


def trade_score(buying: bool, price: int, settle: int) -> int:
    """+1 if the trade made money at the settle (bought below / sold above), −1 if it lost, 0 at the settle.
    One trade is one score, whatever its size."""
    edge = settle - price if buying else price - settle
    return (edge > 0) - (edge < 0)


class OutcrySource:
    """What the shared lobby/custom/stats screens need to know about the game."""

    key = "outcry"
    title = "OUTCRY"
    item = "number"
    config_cls = OutcryConfig
    presets = PRESETS
    events: dict[str, Any] = {}
    places = 0
    tick = 1

    def price(self, x: Any) -> str:
        return f"{x:.0f}"

    def settle_range(self, cfg: OutcryConfig) -> tuple[int, int]:
        u = Universe(players=cfg.players)
        return u.lo * cfg.players, u.hi * cfg.players


OUTCRY_SOURCE = OutcrySource()


# ── records ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Trade:
    round: int
    kind: str  # OPEN_KIND (forced response) / OUTCRY_KIND
    at: int  # tick
    buyer: int
    seller: int
    price: int
    size: int
    aggressor: int  # who crossed: the responder, or the order / take that hit the book


@dataclass(frozen=True)
class Response:
    seat: int
    action: str  # BUY / SELL / PASS / TIMEOUT
    applied: bool  # False: skipped because it would breach someone's limit
    note: str = ""


@dataclass
class Round:
    number: int
    opener: int
    bid: int | None = None
    ask: int | None = None
    auto_quoted: bool = False  # you timed out as opener and the game quoted for you
    responses: list[Response] = field(default_factory=list)  # in the order they were applied
    outcry_start: int | None = None
    outcry_end: int | None = None


@dataclass(frozen=True)
class Echo:
    ok: bool
    text: str


# ── what everyone can see ────────────────────────────────────────────────────


@dataclass(frozen=True)
class PublicReveal:
    """A revealed number: the value and any LOWEST/HIGHEST label. Never who owned it."""

    value: int
    label: str | None


@dataclass(frozen=True)
class PublicState:
    """The table as every player sees it. Holds no number owners (they only appear in the results)."""

    phase: str
    round: int
    rounds: int
    names: tuple[str, ...]
    positions: tuple[int, ...]
    reveals: tuple[PublicReveal, ...]
    opener: str
    quote: tuple[int, int] | None
    responses: tuple[tuple[str, str, bool, str], ...]  # (name, action, applied, note), once applied
    bids: tuple[tuple[str, int], ...]  # (name, price), best first
    offers: tuple[tuple[str, int], ...]
    tape: tuple[Trade, ...]
    last_price: int | None
    seconds_left: float | None
    limit: int
    size: int


@dataclass(frozen=True)
class YouView:
    """Your private view: your number, which reveals were yours, and your exact fair."""

    number: int
    reveals: tuple[SeenReveal, ...]
    fair: FairView
    position: int
    cash: int
    bid: int | None
    offer: int | None


# ── the game ─────────────────────────────────────────────────────────────────

TraderFactory = Callable[["OutcryGame", int, str, random.Random], Trader]


class OutcryGame:
    SOURCE = OUTCRY_SOURCE
    TICK = TICK

    def __init__(self, config: OutcryConfig, mode: str = "CUSTOM", traders: TraderFactory | None = None,
                 universe: Universe | None = None) -> None:
        if not isinstance(config, OutcryConfig):
            raise TypeError("OutcryGame needs an OutcryConfig")
        config.validate()
        self.config = config
        self.mode = mode
        self.seed = config.seed if config.seed is not None else random.SystemRandom().randrange(1, 1_000_000)
        self.universe = universe or Universe(players=config.players)
        self.setup = draw_setup(config, random.Random(self.seed), self.universe)
        self.names = config.names
        n = config.players
        self.max_price = self.universe.hi * n  # highest possible settle: 800 with 8 players
        self.positions = [0] * n
        self.cash = [0] * n
        self.book = Book(config.trade_size, config.limit, self.positions)
        factory = traders or make_trader
        self.traders: dict[int, Trader] = {
            seat: factory(self, seat, self.setup.styles[seat], random.Random(self.setup.trader_seeds[seat]))
            for seat in range(1, n)
        }
        self.trades: list[Trade] = []
        self.rounds: list[Round] = []
        self.revealed = 0
        self.now = 0
        self.deadline: int | None = None
        self.phase = OPEN
        self.next_at: dict[int, int] = {}
        self.pace_ticks = ticks(config.pace_s)
        self.pace_free_at = 0  # first tick the next computer action is allowed
        self.computer_actions: list[tuple[int, int]] = []  # (tick, seat) of every computer outcry action
        self.last_price: int | None = None
        self.your_last_bid: int | None = None  # for the opener auto-quote
        self.your_last_offer: int | None = None
        self.your_response: str | None = None
        self.report_start: int | None = None
        self.reported: int | None = None
        self.report_seconds: float | None = None
        self.log: list[str] = []
        self._start_round()

    @property
    def source(self) -> OutcrySource:
        return OUTCRY_SOURCE

    # ── knowledge ───────────────────────────────────────────────────────────

    def knowledge(self, seat: int) -> Knowledge:
        return knowledge_of(self.setup, seat, self.revealed, self.config.extreme_reveals)

    def fair_view(self, seat: int) -> FairView:
        return fair_view(self.knowledge(seat), self.universe)

    def fair(self, seat: int) -> float:
        return self.fair_view(seat).fair

    def fair_in_round(self, seat: int, number: int) -> float:
        """`seat`'s fair during round `number` (knowledge only changes between rounds)."""
        k = knowledge_of(self.setup, seat, number - 1, self.config.extreme_reveals)
        return fair_view(k, self.universe).fair

    @property
    def round(self) -> Round:
        return self.rounds[-1]

    @property
    def settle(self) -> int:
        return sum(self.setup.numbers)

    def pnl(self, seat: int) -> int:
        return self.cash[seat] + self.positions[seat] * self.settle

    # ── clock ───────────────────────────────────────────────────────────────

    def advance(self, n: int = 1) -> None:
        for _ in range(n):
            self.now += 1
            if self.phase in (OPEN, RESPOND) and self.now >= self.deadline:
                if self.phase == OPEN:
                    self._auto_open()
                else:
                    self._respond(TIMEOUT)
            elif self.phase == OUTCRY:
                self._outcry_tick()
            elif self.phase == REPORT and self.now >= self.deadline:
                self._finish_report(None)

    def advance_to(self, tick: int) -> None:
        if tick > self.now:
            self.advance(tick - self.now)

    def seconds_left(self) -> float | None:
        if self.phase == OUTCRY:
            return max(0, self.round.outcry_end - self.now) * TICK
        if self.phase in (OPEN, RESPOND, REPORT):
            return max(0, self.deadline - self.now) * TICK
        return None

    # ── round start: forced open ────────────────────────────────────────────

    def _start_round(self) -> None:
        number = len(self.rounds) + 1
        r = Round(number, self.setup.openers[number - 1])
        self.rounds.append(r)
        self.book.clear()
        self.your_response = None
        self.deadline = self.now + ticks(self.config.respond_s)
        if r.opener == YOU:
            self.phase = OPEN
            return
        r.bid, r.ask = self.traders[r.opener].open_quote()
        self.phase = RESPOND

    def open_errors(self, bid: Any, ask: Any) -> list[str]:
        """A forced open needs bid ≥ 0, ask ≤ the highest possible settle, and ask > bid. Any width."""
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (bid, ask)):
            return ["bid and ask must be whole numbers"]
        if bid < 0:
            return ["bid can't be negative"]
        if ask > self.max_price:
            return [f"ask can't be above {self.max_price}"]
        if ask <= bid:
            return ["ask must be above bid"]
        return []

    def fit_quote(self, bid: int, ask: int) -> tuple[int, int]:
        """Slide a quote, keeping its width, so that 0 ≤ bid and ask ≤ max_price."""
        shift = max(0, -bid) - max(0, ask - self.max_price)
        return bid + shift, ask + shift

    def player_open(self, bid: int, ask: int) -> None:
        """Your forced open: quote `bid @ ask` to everyone else."""
        if self.phase != OPEN:
            raise RuntimeError("you aren't opening this round")
        errs = self.open_errors(bid, ask)
        if errs:
            raise ValueError(errs[0])
        self.round.bid, self.round.ask = bid, ask
        self._resolve_responses()

    def _auto_open(self) -> None:
        sides = [p for p in (self.your_last_bid, self.your_last_offer) if p is not None]
        mid = sum(sides) / len(sides) if sides else 50 * self.config.players
        bid, ask = self.fit_quote(round(mid - AUTO_HALF_WIDTH), round(mid - AUTO_HALF_WIDTH) + 2 * AUTO_HALF_WIDTH)
        r = self.round
        r.bid, r.ask, r.auto_quoted = bid, ask, True
        source = "your last outcry mid" if sides else "no outcry quotes yet"
        self.log.append(f"R{r.number}: open timer ran out — auto-quoted {bid} @ {ask} ({source} ± {AUTO_HALF_WIDTH})")
        self._resolve_responses()

    # ── forced response ─────────────────────────────────────────────────────

    def player_respond(self, action: str) -> None:
        if self.phase != RESPOND:
            raise RuntimeError("no market to respond to")
        if action not in (BUY, SELL, PASS):
            raise ValueError(f"respond with buy, sell or pass, not {action!r}")
        self._respond(action)

    def _respond(self, action: str) -> None:
        self.your_response = action
        self._resolve_responses()

    def _resolve_responses(self) -> None:
        """Everyone answers blind and at once: every computer decision is made before any is applied.
        They are then applied in this round's (pre-drawn) random order, skipping any that would push
        the responder or the opener past the limit."""
        r = self.round
        decisions = {
            seat: (self.your_response if seat == YOU else self.traders[seat].respond(r.bid, r.ask))
            for seat in range(self.config.players) if seat != r.opener
        }
        size, limit = self.config.trade_size, self.config.limit
        for seat in self.setup.response_orders[r.number - 1]:
            if seat == r.opener:
                continue
            action = decisions[seat]
            if action not in (BUY, SELL):
                r.responses.append(Response(seat, action, True))
                continue
            buyer, seller = (seat, r.opener) if action == BUY else (r.opener, seat)
            blocked = [s for s, d in ((buyer, size), (seller, -size)) if abs(self.positions[s] + d) > limit]
            if blocked:
                note = f"skipped — {self.names[blocked[0]]} at the ±{limit} limit"
                r.responses.append(Response(seat, action, False, note))
                self.log.append(f"R{r.number}: {self.names[seat]} {action} {note}")
                continue
            self._fill(buyer, seller, r.ask if action == BUY else r.bid, seat, OPEN_KIND)
            r.responses.append(Response(seat, action, True))
        self._start_outcry()

    # ── open outcry ─────────────────────────────────────────────────────────

    def _start_outcry(self) -> None:
        r = self.round
        self.phase = OUTCRY
        self.deadline = None
        r.outcry_start = self.now
        r.outcry_end = self.now + ticks(self.config.outcry_s)
        self.pace_free_at = self.now
        self.next_at = {seat: self.now + t.cooldown_ticks() for seat, t in self.traders.items()}

    def _outcry_tick(self) -> None:
        """Traders whose cooldown is up take turns in seat order, starting one seat later each tick. The
        table-wide pace cap allows at most one computer action (anything that posts, replaces, cancels or
        takes) per `pace_s`; traders still waiting keep their place. A turn that changes nothing doesn't
        use the slot. Your commands never go through here, so the cap never limits you."""
        if self.now >= self.round.outcry_end:
            self._close()
            return
        if self.now < self.pace_free_at:
            return
        seats = list(self.traders)
        k = self.now % len(seats)
        for seat in seats[k:] + seats[:k]:
            if self.next_at[seat] > self.now:
                continue
            trader = self.traders[seat]
            before = self._book_state()
            trader.act()
            self.next_at[seat] = self.now + trader.cooldown_ticks()
            if self._book_state() != before:
                self.computer_actions.append((self.now, seat))
                self.pace_free_at = self.now + self.pace_ticks
                return

    def _book_state(self) -> tuple:
        return tuple(self.book.bids), tuple(self.book.offers), len(self.trades)

    def place(self, seat: int, side: str, price: int) -> Result:
        """Post a limit order for `seat` (outcry only); a crossing order trades immediately."""
        self._require_outcry()
        result = self.book.place(seat, side, price)
        if result.ok and seat == YOU:
            if side == BID:
                self.your_last_bid = price
            else:
                self.your_last_offer = price
        self._settle_result(result)
        return result

    def take(self, seat: int, side: str) -> Result:
        """Lift the best offer (BID) or hit the best bid (OFFER) from someone else."""
        self._require_outcry()
        result = self.book.take(seat, side)
        self._settle_result(result)
        return result

    def cancel(self, seat: int, side: str | None = None) -> int:
        return len(self.book.cancel(seat, side))

    def _settle_result(self, result: Result) -> None:
        if result.fill:
            f = result.fill
            self._fill(f.buyer, f.seller, f.price, f.aggressor, OUTCRY_KIND)

    def _require_outcry(self) -> None:
        if self.phase != OUTCRY:
            raise RuntimeError("the outcry isn't open")

    def _fill(self, buyer: int, seller: int, price: int, aggressor: int, kind: str) -> None:
        size = self.config.trade_size
        self.positions[buyer] += size
        self.positions[seller] -= size
        self.cash[buyer] -= size * price
        self.cash[seller] += size * price
        trade = Trade(self.round.number, kind, self.now, buyer, seller, price, size, aggressor)
        self.trades.append(trade)
        self.last_price = price
        for trader in self.traders.values():
            trader.on_trade(trade)

    # ── your commands ───────────────────────────────────────────────────────

    def command(self, text: str) -> list[Echo]:
        """Run one command-line command for you. Bad input is never sent to the book."""
        if self.phase != OUTCRY:
            return [Echo(False, "✗ the outcry isn't open")]
        try:
            cmd = parse_command(text)
        except CommandError as e:
            return [Echo(False, f"✗ {e}")]
        if cmd.kind == BID_CMD:
            return [self._order_echo(BID, cmd.bid)]
        if cmd.kind == OFFER_CMD:
            return [self._order_echo(OFFER, cmd.ask)]
        if cmd.kind == BOTH:
            return [self._order_echo(BID, cmd.bid), self._order_echo(OFFER, cmd.ask)]
        if cmd.kind in (LIFT, HIT):
            result = self.take(YOU, BID if cmd.kind == LIFT else OFFER)
            if not result.ok:
                return [Echo(False, f"✗ {result.error}")]
            return [Echo(True, f"✓ {self._fill_text(result)}")]
        side = {CANCEL_ALL: None, CANCEL_BID: BID, CANCEL_OFFER: OFFER}[cmd.kind]
        gone = self.cancel(YOU, side)
        what = {None: "all orders", BID: "your bid", OFFER: "your offer"}[side]
        return [Echo(True, f"✓ cancelled {what}" if gone else f"✓ nothing to cancel ({what})")]

    def _order_echo(self, side: str, price: int) -> Echo:
        result = self.place(YOU, side, price)
        word = "bid" if side == BID else "offer"
        if not result.ok:
            return Echo(False, f"✗ {word} {price}: {result.error}")
        if result.fill:
            return Echo(True, f"✓ {word} {price} → {self._fill_text(result)}")
        return Echo(True, f"✓ {word} {price} posted")

    def _fill_text(self, result: Result) -> str:
        f = result.fill
        if f.buyer == YOU:
            return f"bought {f.size} @ {f.price} from {self.names[f.seller]}"
        return f"sold {f.size} @ {f.price} to {self.names[f.buyer]}"

    # ── close, reveal, report ───────────────────────────────────────────────

    def _close(self) -> None:
        self.book.clear()
        self.revealed += 1
        self.phase = CLOSED

    def next_round(self) -> None:
        """After a round's reveal: start the next round, or the final reveal and your P&L report."""
        if self.phase != CLOSED:
            raise RuntimeError("the round isn't closed")
        if len(self.rounds) < self.config.rounds:
            self._start_round()
            return
        self.revealed = self.config.players
        self.phase = REPORT
        self.report_start = self.now
        self.deadline = self.now + ticks(self.config.report_s)

    def score(self, seat: int = YOU) -> int:
        """Net trade score: the sum of trade_score over every trade `seat` was in."""
        return sum(trade_score(t.buyer == seat, t.price, self.settle) for t in self.trades if seat in (t.buyer, t.seller))

    def report(self, value: Any) -> bool:
        """Your net trade score report: an integer (negatives allowed), exact match. Returns whether it was right."""
        if self.phase != REPORT:
            raise RuntimeError("nothing to report yet")
        reported = int(str(value).strip())
        self._finish_report(reported)
        return reported == self.score(YOU)

    def _finish_report(self, value: int | None) -> None:
        self.reported = value
        self.report_seconds = (self.now - self.report_start) * TICK
        self.phase = RESULTS

    @property
    def report_correct(self) -> bool:
        """A timeout (no report) counts as wrong."""
        return self.reported is not None and self.reported == self.score(YOU)

    # ── views ───────────────────────────────────────────────────────────────

    def public(self) -> PublicState:
        r = self.round
        reveals = tuple(
            PublicReveal(self.setup.numbers[seat], label)
            for seat, label in zip(self.setup.reveal_order[: self.revealed], self.setup.reveal_labels[: self.revealed])
        )
        applied = self.phase not in (OPEN, RESPOND)
        return PublicState(
            phase=self.phase, round=r.number, rounds=self.config.rounds, names=self.names,
            positions=tuple(self.positions), reveals=reveals, opener=self.names[r.opener],
            quote=None if r.bid is None else (r.bid, r.ask),
            responses=tuple((self.names[x.seat], x.action, x.applied, x.note) for x in r.responses) if applied else (),
            bids=tuple((self.names[o.owner], o.price) for o in self.book.sorted_bids()),
            offers=tuple((self.names[o.owner], o.price) for o in self.book.sorted_offers()),
            tape=tuple(self.trades), last_price=self.last_price, seconds_left=self.seconds_left(),
            limit=self.config.limit, size=self.config.trade_size,
        )

    def you(self) -> YouView:
        k = self.knowledge(YOU)
        bid, offer = self.book.order_of(YOU, BID), self.book.order_of(YOU, OFFER)
        return YouView(
            number=k.own, reveals=k.reveals, fair=self.fair_view(YOU), position=self.positions[YOU],
            cash=self.cash[YOU], bid=bid.price if bid else None, offer=offer.price if offer else None,
        )

    def results(self) -> Any:
        """Everything, owners included. Only after your report."""
        if self.phase != RESULTS:
            raise RuntimeError("results are hidden until the game is over")
        from met_games.games.outcry.stats import results

        return results(self)
