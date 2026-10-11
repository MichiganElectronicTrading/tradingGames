"""Trading Game engine: one deal per hand, four turns of two-way markets, settlement at the sum.

You and three computer traders (DELTA, GAMMA, THETA) sit at a table. Each hand deals cards with
Card's rules and source (values, events, fair value, range). On turn i the player in seat i
makes a market and the other three may trade it; positions and cash carry across the turns.
After turn 4 every position settles at the sum of the cards, and the four hand P&Ls sum to 0.

Pure Python. The UI drives a session and reads its state; nothing here knows about Textual.

Every random draw of a hand (deal, face-up count, event, doubled card, seat order, peeks, flip
schedule) is made in `new_hand`, and the computer traders make no random choices, so a seed plus
the player's inputs replays exactly. Money is whole dollars (ints), so P&L is exact.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from met_games.games.card.deck import Card
from met_games.games.card.engine import CardSource
from met_games.games.sumgame.engine import BUY, PASS, SELL, TIMEOUT, deal_items, make_quote
from met_games.games.sumgame.source import DOUBLE_HIDDEN, Market
from met_games.games.trade.config import PRESETS, TradeConfig

YOU, DELTA, GAMMA, THETA = "YOU", "DELTA", "GAMMA", "THETA"
PLAYERS = (YOU, DELTA, GAMMA, THETA)
TRADERS = (DELTA, GAMMA, THETA)  # trader j = TRADERS[j] for peek assignment
TURNS = 4
TRADER_SIZE = 5  # a computer maker's size per side, and the most a computer taker takes
TRADER_EDGE = 1  # a computer taker needs est ≥ ask + 1 to buy, est ≤ bid − 1 to sell


class TradeSource(CardSource):
    key = "trade"
    title = "TRADING GAME"
    config_cls = TradeConfig
    presets = PRESETS


TRADE = TradeSource()


# ── pure rules ───────────────────────────────────────────────────────────────


def peek_assignment(peekable: list[int], rng: random.Random, single: bool) -> dict[str, int | None]:
    """Which hidden card each trader peeks at. With ≥ 3 peekable cards the three traders see distinct
    random ones; with fewer, trader j sees peekable[j mod k]; with none, nobody peeks. `single`
    (Easy) keeps one random trader's peek and blanks the other two."""
    k = len(peekable)
    if k == 0:
        return {t: None for t in TRADERS}
    cards = rng.sample(peekable, 3) if k >= 3 else [peekable[j % k] for j in range(3)]
    peeks: dict[str, int | None] = dict(zip(TRADERS, cards))
    if single:
        keep = rng.choice(TRADERS)
        peeks = {t: (c if t == keep else None) for t, c in peeks.items()}
    return peeks


def flip_schedule(hidden: list[int], doubled: int | None, rng: random.Random) -> list[int | None]:
    """The cards that flip face up after turns 1, 2 and 3 (Hard). Never the last hidden card, and
    never the doubled card (it stays hidden); None when nothing can flip."""
    hidden = list(hidden)
    flips: list[int | None] = []
    for _ in range(TURNS - 1):
        candidates = [i for i in hidden if i != doubled] if len(hidden) >= 2 else []
        if candidates:
            i = rng.choice(candidates)
            hidden.remove(i)
            flips.append(i)
        else:
            flips.append(None)
    return flips


def clamp(x: float, lo: float, hi: float) -> float:
    return min(max(x, lo), hi)


def computer_quote(public_fair: float, est: float, width: int) -> tuple[int, int]:
    """mid = public_fair + 0.5 × (est − public_fair); bid = round(mid − w/2); ask = bid + w."""
    return make_quote(public_fair, 0.5 * (est - public_fair), width)


def computer_take(est: float, bid: int, ask: int, bid_left: int, ask_left: int) -> tuple[str, int, str | None]:
    """(action, size, wanted). Buy min(5, ask_left) at the ask if est ≥ ask + 1; sell min(5, bid_left)
    at the bid if est ≤ bid − 1; otherwise pass. A trader whose side is used up passes, and
    `wanted` records the side it would have taken."""
    if est >= ask + TRADER_EDGE:
        want, left = BUY, ask_left
    elif est <= bid - TRADER_EDGE:
        want, left = SELL, bid_left
    else:
        return PASS, 0, None
    size = min(TRADER_SIZE, left)
    return (want, size, None) if size else (PASS, 0, want)


def position_pnl(cash: int, position: int, settle: int) -> int:
    return cash + position * settle


def worst_loss(cash: int, position: int, settle_min: int, settle_max: int) -> int:
    """P&L is linear in the settle, so the worst case is at one end of the range (0 if neither loses)."""
    return max(0, -min(position_pnl(cash, position, settle_min), position_pnl(cash, position, settle_max)))


# ── hand state ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Action:
    """One taker's decision on a market. BUY/SELL are the taker's (aggressor's) side."""

    who: str
    action: str  # BUY / SELL / PASS / TIMEOUT
    size: int  # units filled (0 for a pass or timeout)
    price: int | None  # fill price
    table_fair: float  # fair given face-up + every peeked card, when the action happened
    wanted: str | None = None  # a trader that passed only because the side it wanted was used up

    @property
    def is_fill(self) -> bool:
        return self.size > 0


@dataclass
class Turn:
    number: int  # 1..4
    maker: str
    up: tuple[int, ...]  # face-up card indices during this turn
    flipped: int | None = None  # card that turned face up just before this turn
    bid: int | None = None  # None: the player posted no market
    ask: int | None = None
    size: int = 0  # per side
    bid_left: int = 0
    ask_left: int = 0
    actions: list[Action] = field(default_factory=list)
    timed_out: bool = False  # the player's quote or take timer ran out
    done: bool = False

    @property
    def posted(self) -> bool:
        return self.bid is not None

    @property
    def width(self) -> int | None:
        return None if self.bid is None else self.ask - self.bid

    @property
    def fills(self) -> list[Action]:
        return [a for a in self.actions if a.is_fill]

    @property
    def bid_filled(self) -> int:
        """Units the maker bought (takers sold into the bid)."""
        return sum(a.size for a in self.fills if a.action == SELL)

    @property
    def ask_filled(self) -> int:
        """Units the maker sold (takers bought the ask)."""
        return sum(a.size for a in self.fills if a.action == BUY)

    def action_of(self, who: str) -> Action | None:
        return next((a for a in self.actions if a.who == who), None)


@dataclass
class Hand:
    SOURCE: ClassVar[TradeSource] = TRADE

    number: int
    items: list[Card]
    event: str | None
    doubled: int | None  # hidden card that counts twice (double_hidden); never peeked or flipped
    face_up: list[int]  # indices, in the order they became visible
    seats: tuple[str, ...]  # seat i makes on turn i + 1
    peeks: dict[str, int | None]
    flips: list[int | None]  # card that flips after turns 1, 2, 3
    learn_rate: float
    balance_before: int
    turns: list[Turn] = field(default_factory=list)
    offsets: dict[str, float] = field(default_factory=lambda: {t: 0.0 for t in TRADERS})
    position: dict[str, int] = field(default_factory=lambda: {p: 0 for p in PLAYERS})
    cash: dict[str, int] = field(default_factory=lambda: {p: 0 for p in PLAYERS})
    settled: bool = False
    balance_after: int | None = None
    reported: int | None = None
    answer_time: float | None = None

    # ── cards ───────────────────────────────────────────────────────────────

    @property
    def hidden(self) -> list[int]:
        return [i for i in range(len(self.items)) if i not in self.face_up]

    @property
    def values(self) -> list[int]:
        return [self.SOURCE.value(c, self.event) for c in self.items]

    @property
    def settle(self) -> int:
        values = self.values
        return sum(values) + (values[self.doubled] if self.doubled is not None else 0)

    def market_given(self, known: Iterable[int | None] = ()) -> Market:
        """Card's fair value and range treating the face-up cards plus `known` hidden cards as seen."""
        seen = list(self.face_up) + [i for i in dict.fromkeys(known) if i is not None and i not in self.face_up]
        return self.SOURCE.market([self.items[i] for i in seen], self.event, len(self.items) - len(seen))

    def public(self) -> Market:
        return self.market_given()

    def private(self, trader: str) -> Market:
        """What `trader` knows: face-up cards plus its peeked card while that card is still hidden."""
        return self.market_given([self.peeks[trader]])

    def table(self) -> Market:
        """Fair given the face-up cards plus every card any trader peeked at."""
        return self.market_given(self.peeks[t] for t in TRADERS)

    def est(self, trader: str) -> float:
        m = self.private(trader)
        return clamp(m.fair + self.offsets[trader], m.settle_min, m.settle_max)

    # ── turns ───────────────────────────────────────────────────────────────

    @property
    def turn(self) -> Turn:
        return self.turns[-1]

    def seat_of(self, who: str) -> int:
        return self.seats.index(who)

    def your_turn(self) -> Turn:
        return self.turns[self.seat_of(YOU)]

    # ── P&L ─────────────────────────────────────────────────────────────────

    def pnl(self, who: str) -> int:
        return position_pnl(self.cash[who], self.position[who], self.settle)

    def pnls(self) -> dict[str, int]:
        return {p: self.pnl(p) for p in PLAYERS}

    def ranks(self) -> dict[str, int]:
        """Competition ranking by hand P&L (ties share a rank)."""
        pnls = self.pnls()
        return {p: 1 + sum(1 for q in PLAYERS if pnls[q] > pnls[p]) for p in PLAYERS}

    def fill_pnl(self, turn: Turn, a: Action, who: str = YOU) -> int:
        """`who`'s P&L from one fill (0 if `who` is neither side)."""
        if not a.is_fill or who not in (turn.maker, a.who):
            return 0
        buys = (a.action == BUY) == (who == a.who)
        return (self.settle - a.price) * a.size * (1 if buys else -1)

    @property
    def making_pnl(self) -> int:
        """Your P&L from fills on your own market, settled at the sum."""
        return sum(self.fill_pnl(t, a) for t in self.turns if t.maker == YOU for a in t.fills)

    @property
    def taking_pnl(self) -> int:
        """Your P&L from your trades on the others' markets."""
        return sum(self.fill_pnl(t, a) for t in self.turns if t.maker != YOU for a in t.fills if a.who == YOU)

    @property
    def report_correct(self) -> bool | None:
        return None if self.reported is None else self.reported == self.pnl(YOU)


# ── session ──────────────────────────────────────────────────────────────────


class TradeSession:
    ROUND: ClassVar[type[Hand]] = Hand  # the shared GameUI finds the source through it

    def __init__(self, config: TradeConfig, mode: str = "CUSTOM") -> None:
        if not isinstance(config, TradeConfig):
            raise TypeError("TradeSession needs a TradeConfig")
        config.validate()
        self.config = config
        self.mode = mode
        self.seed = config.seed if config.seed is not None else random.SystemRandom().randrange(1, 1_000_000)
        self.rng = random.Random(self.seed)
        self.balance: int = config.budget
        self.hands: list[Hand] = []
        self.totals: dict[str, int] = {p: 0 for p in PLAYERS}  # cumulative P&L of settled hands

    @property
    def source(self) -> TradeSource:
        return TRADE

    @property
    def current(self) -> Hand | None:
        return self.hands[-1] if self.hands else None

    @property
    def finished(self) -> bool:
        return len(self.hands) >= self.config.hands and self.current is not None and self.current.settled

    # ── hand start ──────────────────────────────────────────────────────────

    def new_hand(self) -> Hand:
        """Deal the next hand and open turn 1. Draw order: card count, face-up count, event, the deal,
        the doubled card, seat order, peeks, flip schedule."""
        if self.finished:
            raise RuntimeError("session is finished")
        if self.current is not None and not self.current.settled:
            raise RuntimeError("current hand is still open")
        cfg, rng = self.config, self.rng
        items, n_up, event = deal_items(TRADE, cfg, rng)
        hidden = list(range(n_up, len(items)))
        doubled = rng.choice(hidden) if event == DOUBLE_HIDDEN else None
        seats = tuple(rng.sample(PLAYERS, len(PLAYERS)))
        peeks = peek_assignment([i for i in hidden if i != doubled], rng, single=cfg.peeks == "one")
        flips = flip_schedule(hidden, doubled, rng) if cfg.flip_between_turns else [None] * (TURNS - 1)
        hand = Hand(
            number=len(self.hands) + 1, items=items, event=event, doubled=doubled, face_up=list(range(n_up)),
            seats=seats, peeks=peeks, flips=flips, learn_rate=cfg.learn_rate, balance_before=self.balance,
        )
        self.hands.append(hand)
        self._open_turn(hand, None)
        return hand

    def _open_turn(self, hand: Hand, flipped: int | None) -> Turn:
        maker = hand.seats[len(hand.turns)]
        turn = Turn(number=len(hand.turns) + 1, maker=maker, up=tuple(hand.face_up), flipped=flipped)
        hand.turns.append(turn)
        if maker != YOU:
            bid, ask = computer_quote(hand.public().fair, hand.est(maker), self.config.trader_width)
            self._post(turn, bid, ask, TRADER_SIZE)
        return turn

    @staticmethod
    def _post(turn: Turn, bid: int, ask: int, size: int) -> None:
        turn.bid, turn.ask, turn.size = bid, ask, size
        turn.bid_left = turn.ask_left = size

    # ── the player's risk ───────────────────────────────────────────────────

    def worst_after(self, d_cash: int, d_position: int) -> int:
        """Your worst-case hand loss if your cash and position changed by these amounts."""
        hand = self._hand()
        m = hand.public()
        return worst_loss(hand.cash[YOU] + d_cash, hand.position[YOU] + d_position, m.settle_min, m.settle_max)

    def quote_risk(self, bid: int, ask: int, size: int) -> list[tuple[str, int]]:
        """Worst-case loss of your hand if all of the bid fills, all of the ask fills, and both fill."""
        return [
            ("bid fills", self.worst_after(-size * bid, size)),
            ("ask fills", self.worst_after(size * ask, -size)),
            ("both fill", self.worst_after(size * (ask - bid), 0)),
        ]

    def quote_errors(self, bid: Any, ask: Any, size: Any) -> list[str]:
        cfg = self.config
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (bid, ask, size)):
            return ["bid, ask and size must be whole numbers"]
        errs = []
        width = ask - bid
        if not cfg.width_min <= width <= cfg.width_max:
            errs.append(f"width {width} is outside the allowed {cfg.width_min}–{cfg.width_max}")
        if cfg.sizing == "fixed" and size != cfg.FIXED_SIZE:
            errs.append(f"size is fixed at {cfg.FIXED_SIZE}")
        elif not 1 <= size <= cfg.SIZE_MAX:
            errs.append(f"size must be 1–{cfg.SIZE_MAX}")
        if not errs:
            for case, loss in self.quote_risk(bid, ask, size):
                if loss > self.balance:
                    errs.append(f"if {case}, your worst case is −${loss} > balance ${self.balance}")
                    break
        return errs

    def take_limits(self) -> tuple[int, int]:
        """(max_buy, max_sell): the most you can take on each side of the open market, capped by its
        remaining size and by the risk rule (0 = side disabled)."""
        turn = self._takeable()

        def cap(sign: int, price: int, left: int) -> int:
            n = left
            while n > 0 and self.worst_after(-sign * n * price, sign * n) > self.balance:
                n -= 1
            return n

        return cap(1, turn.ask, turn.ask_left), cap(-1, turn.bid, turn.bid_left)

    # ── the player's actions ────────────────────────────────────────────────

    def post_quote(self, bid: int, ask: int, size: int) -> Turn:
        """Post your market; the computer traders then act on it in seat order."""
        turn = self._your_market()
        errs = self.quote_errors(bid, ask, size)
        if errs:
            raise ValueError(errs[0])
        self._post(turn, bid, ask, size)
        self._traders_act(turn)
        turn.done = True
        return turn

    def no_quote(self) -> Turn:
        """Your quote timer ran out: you post nothing and the turn passes with no trades."""
        turn = self._your_market()
        turn.timed_out = turn.done = True
        return turn

    def take(self, action: str, size: int) -> Turn:
        """Buy at the ask or sell at the bid of a computer trader's market. You act first; the other
        traders act after you."""
        turn = self._takeable()
        if action not in (BUY, SELL):
            raise ValueError(f"not a trade: {action!r}")
        max_buy, max_sell = self.take_limits()
        cap = max_buy if action == BUY else max_sell
        if not 1 <= size <= cap:
            raise ValueError(f"size {size} outside allowed 1–{cap}")
        self._fill(turn, YOU, action, size)
        return self._finish_take(turn)

    def pass_(self) -> Turn:
        turn = self._takeable()
        turn.actions.append(Action(YOU, PASS, 0, None, self._hand().table().fair))
        return self._finish_take(turn)

    def timeout(self) -> Turn:
        turn = self._takeable()
        turn.actions.append(Action(YOU, TIMEOUT, 0, None, self._hand().table().fair))
        turn.timed_out = True
        return self._finish_take(turn)

    def _finish_take(self, turn: Turn) -> Turn:
        self._traders_act(turn)
        turn.done = True
        return turn

    # ── flow ────────────────────────────────────────────────────────────────

    def next_turn(self) -> Turn | None:
        """Open the next turn (after any between-turn flip), or settle the hand after turn 4 and
        return None."""
        hand = self._hand()
        if hand.settled or not hand.turn.done:
            raise RuntimeError("the current turn is still open")
        if len(hand.turns) == TURNS:
            self._settle(hand)
            return None
        flipped = hand.flips[len(hand.turns) - 1]
        if flipped is not None:
            hand.face_up.append(flipped)
        return self._open_turn(hand, flipped)

    def report(self, value: Any, answer_time: float) -> bool:
        """Record your hand P&L report (an integer; correct = exact match)."""
        hand = self._hand()
        if not hand.settled:
            raise RuntimeError("nothing to report yet")
        if hand.reported is not None:
            raise RuntimeError("P&L already reported")
        hand.reported = int(str(value).strip())
        hand.answer_time = answer_time
        return bool(hand.report_correct)

    # ── internals ───────────────────────────────────────────────────────────

    def _hand(self) -> Hand:
        if self.current is None:
            raise RuntimeError("no hand dealt")
        return self.current

    def _open(self) -> Turn:
        hand = self._hand()
        if hand.settled or hand.turn.done:
            raise RuntimeError("no open turn")
        return hand.turn

    def _your_market(self) -> Turn:
        turn = self._open()
        if turn.maker != YOU:
            raise RuntimeError(f"{turn.maker} is making this turn")
        return turn

    def _takeable(self) -> Turn:
        turn = self._open()
        if turn.maker == YOU:
            raise RuntimeError("you are making this turn")
        if turn.action_of(YOU) is not None:
            raise RuntimeError("you already acted this turn")
        return turn

    def _traders_act(self, turn: Turn) -> None:
        hand = self._hand()
        for who in hand.seats:
            if who in (YOU, turn.maker):
                continue
            action, size, wanted = computer_take(hand.est(who), turn.bid, turn.ask, turn.bid_left, turn.ask_left)
            if size:
                self._fill(turn, who, action, size)
            else:
                turn.actions.append(Action(who, PASS, 0, None, hand.table().fair, wanted))

    def _fill(self, turn: Turn, taker: str, side: str, size: int) -> None:
        hand = self._hand()
        price = turn.ask if side == BUY else turn.bid
        sign = 1 if side == BUY else -1
        hand.position[taker] += sign * size
        hand.cash[taker] -= sign * size * price
        hand.position[turn.maker] -= sign * size
        hand.cash[turn.maker] += sign * size * price
        if side == BUY:
            turn.ask_left -= size
        else:
            turn.bid_left -= size
        turn.actions.append(Action(taker, side, size, price, hand.table().fair))
        self._learn(hand, price, side)

    @staticmethod
    def _learn(hand: Hand, price: int, side: str) -> None:
        """After every fill each trader moves its offset toward what the aggressor revealed:
        offset += learn_rate × (target − est), target = price + 1 after a buy, price − 1 after a sell."""
        if hand.learn_rate == 0:
            return
        target = price + 1 if side == BUY else price - 1
        for t in TRADERS:
            hand.offsets[t] += hand.learn_rate * (target - hand.est(t))

    def _settle(self, hand: Hand) -> None:
        pnls = hand.pnls()
        if sum(pnls.values()) != 0:
            raise AssertionError(f"hand P&Ls must sum to 0, got {pnls}")
        hand.settled = True
        for p, x in pnls.items():
            self.totals[p] += x
        self.balance += pnls[YOU]
        hand.balance_after = self.balance
