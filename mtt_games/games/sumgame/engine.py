"""Shared sum-game engine: round state machine, quotes, risk limits, P&L, edge and verdicts.

Pure Python. The UI drives a session and reads its state; nothing here knows about Textual.
Each game plugs in a Source (deal, values, fair value, range) by subclassing Round and SumSession.

All randomness comes from the session's single `random.Random(seed)`, and every random draw a
round could need is made when the round starts, so a session replays exactly from its seed
regardless of when the player acts.

Money is exact: prices are ints when the tick is 1 and Decimals on a fractional tick (multiples
of the tick), so P&L, balances and report checks never see float drift. Fair value and edge are
expectations and stay floats.
"""

from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from dataclasses import dataclass, field
from typing import Any, ClassVar

from mtt_games.games.sumgame.config import SumConfig
from mtt_games.games.sumgame.source import DOUBLE_HIDDEN, Market, Source

BUY, SELL, PASS, TIMEOUT = "buy", "sell", "pass", "timeout"
SIZE_CAP = 100
MISSED_EDGE = 1.0  # a pass that skipped at least this much edge per unit is a mistake
BROKE = "balance hit $0"
OUT_OF_RISK = "out of risk capacity"
CENT = Decimal("0.01")

Money = int | Decimal


# ── pure math ────────────────────────────────────────────────────────────────


def round_to_tick(x: float, tick: Money = 1) -> Money:
    """Nearest multiple of `tick` (ties to even); exact int or Decimal, never a float."""
    return round(x / float(tick)) * tick


def make_quote(fair: float, noise: float, spread: Money, tick: Money = 1) -> tuple[Money, Money]:
    mid = fair + noise
    bid = round_to_tick(mid - float(spread) / 2, tick)
    return bid, bid + spread


def risk_limits(
    balance: Money, bid: Money, ask: Money, settle_min: int, settle_max: int, cap: int = SIZE_CAP
) -> tuple[int, int]:
    """(max_long, max_short): largest sizes whose worst-case loss fits in the balance."""

    def side(worst_per_unit: Money) -> int:
        if worst_per_unit <= 0:
            return cap
        return max(0, min(cap, int(balance // worst_per_unit)))

    return side(ask - settle_min), side(settle_max - bid)


def trade_pnl(action: str, size: int, bid: Money, ask: Money, settle: int) -> Money:
    if action == BUY:
        return (settle - ask) * size
    if action == SELL:
        return (bid - settle) * size
    return 0


def edge_per_unit(action: str, fair: float, bid: Money, ask: Money) -> float:
    if action == BUY:
        return fair - float(ask)
    if action == SELL:
        return float(bid) - fair
    raise ValueError(f"no edge for {action!r}")


def to_cents(x: Any) -> Decimal:
    """Parse a P&L (int, Decimal, str like '17.5' / '17.50' / '17.499') and round it to cents."""
    try:
        return Decimal(str(x).strip()).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"not a number: {x!r}") from None


def deal_items(source: Source, cfg: SumConfig, rng: random.Random) -> tuple[list[Any], int, str | None]:
    """Draw a deal under `cfg`: (items, face-up count, event). The first `n_up` items are face up.

    Draw order: item count, face-up count, event, then the deal itself."""
    n = rng.randint(cfg.n_min, cfg.n_max)
    n_up = rng.randint(cfg.face_up_min, cfg.face_up_max)
    k = n - n_up
    event = None
    if cfg.event_freq > 0 and rng.random() < cfg.event_freq:
        candidates = [e for e in cfg.enabled_events if not (e == DOUBLE_HIDDEN and k == 0)]
        if candidates:
            event = rng.choice(candidates)
    return source.deal(rng, n, event), n_up, event


# ── round + session state ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Decision:
    action: str  # BUY / SELL / PASS / TIMEOUT
    size: int  # 0 for pass / timeout
    t: float  # seconds into the round
    bid: Money
    ask: Money
    market: Market  # what was knowable at the moment of the decision
    max_long: int
    max_short: int

    @property
    def is_trade(self) -> bool:
        return self.action in (BUY, SELL)

    @property
    def price(self) -> Money | None:
        return {BUY: self.ask, SELL: self.bid}.get(self.action)

    @property
    def fair(self) -> float:
        return self.market.fair

    @property
    def edge_per_unit(self) -> float | None:
        return edge_per_unit(self.action, self.fair, self.bid, self.ask) if self.is_trade else None

    @property
    def edge_dollars(self) -> float:
        return self.edge_per_unit * self.size if self.is_trade else 0.0

    @property
    def best_edge(self) -> float:
        """Best per-unit edge among the sides the player was allowed to trade (0 if none)."""
        sides = [s for s, cap in ((BUY, self.max_long), (SELL, self.max_short)) if cap >= 1]
        return max((edge_per_unit(s, self.fair, self.bid, self.ask) for s in sides), default=0.0)


@dataclass
class Round:
    SOURCE: ClassVar[Source]  # set by each game's Round subclass

    number: int
    items: list[Any]
    event: str | None
    face_up: list[int]  # indices into `items`, in the order they became visible
    doubled: int | None  # index of the hidden item that counts twice (double_hidden)
    timer_s: int
    balance_before: Money
    flip_at: float | None = None
    flip_index: int | None = None
    flip_stale: bool = False
    flip_noise: float = 0.0
    flipped_at: float | None = None
    tape: list[tuple[float, Money, Money]] = field(default_factory=list)  # (t, bid, ask)
    decision: Decision | None = None
    balance_after: Money | None = None
    reported: Decimal | None = None
    answer_time: float | None = None

    @property
    def hidden(self) -> list[int]:
        return [i for i in range(len(self.items)) if i not in self.face_up]

    @property
    def values(self) -> list[int]:
        return [self.SOURCE.value(item, self.event) for item in self.items]

    def market(self) -> Market:
        return self.SOURCE.market([self.items[i] for i in self.face_up], self.event, len(self.hidden))

    @property
    def bid(self) -> Money:
        return self.tape[-1][1]

    @property
    def ask(self) -> Money:
        return self.tape[-1][2]

    @property
    def settle(self) -> int:
        values = self.values
        return sum(values) + (values[self.doubled] if self.doubled is not None else 0)

    @property
    def pnl(self) -> Money:
        d = self._decided()
        return trade_pnl(d.action, d.size, d.bid, d.ask, self.settle)

    @property
    def report_correct(self) -> bool | None:
        return None if self.reported is None else to_cents(self.reported) == to_cents(self.pnl)

    @property
    def verdict(self) -> str:
        d = self._decided()
        if d.action == TIMEOUT:
            return "timed out"
        if d.action == PASS:
            return f"missed edge of {d.best_edge:.2f}/unit" if d.best_edge >= MISSED_EDGE else "correct pass"
        trade = "good trade" if d.edge_per_unit >= 0 else "bad trade"
        if d.edge_per_unit >= 0:
            return f"{trade}, {'good draw' if self.pnl >= 0 else 'bad draw'}"
        return f"{trade}, {'lucky' if self.pnl >= 0 else 'unlucky'}"

    def _decided(self) -> Decision:
        if self.decision is None:
            raise RuntimeError("round has no decision yet")
        return self.decision


class SumSession:
    ROUND: ClassVar[type[Round]]  # set by each game's session subclass

    def __init__(self, config: SumConfig, mode: str = "CUSTOM") -> None:
        if not isinstance(config, self.source.config_cls):
            raise TypeError(f"{type(self).__name__} needs a {self.source.config_cls.__name__}")
        config.validate()
        self.config = config
        self.mode = mode
        self.seed = config.seed if config.seed is not None else random.SystemRandom().randrange(1, 1_000_000)
        self.rng = random.Random(self.seed)
        self.balance: Money = self.source.to_money(config.budget)
        self.rounds: list[Round] = []
        self.out_of_risk = False  # set when a new round's quote left no tradable side

    @property
    def source(self) -> Source:
        return self.ROUND.SOURCE

    @property
    def current(self) -> Round | None:
        return self.rounds[-1] if self.rounds else None

    @property
    def end_reason(self) -> str | None:
        """Why the session ended early (None while it is running or after playing every round)."""
        if self.out_of_risk:
            return OUT_OF_RISK
        if self.current is not None and self.current.decision is not None and self.balance <= 0:
            return BROKE
        return None

    @property
    def finished(self) -> bool:
        if self.end_reason is not None:
            return True
        if self.current is None or self.current.decision is None:
            return False
        return len(self.rounds) >= self.config.rounds

    def new_round(self) -> Round | None:
        """Deal the next round. If neither side is tradable at the opening quote (max_long < 1 and
        max_short < 1), the round is not played: the session ends out of risk capacity and this
        returns None."""
        if self.finished:
            raise RuntimeError("session is finished")
        if self.current is not None and self.current.decision is None:
            raise RuntimeError("current round is still open")
        cfg, rng = self.config, self.rng
        items, n_up, event = deal_items(self.source, cfg, rng)
        n, k = len(items), len(items) - n_up
        hidden = list(range(n_up, n))
        rnd = self.ROUND(
            number=len(self.rounds) + 1, items=items, event=event, face_up=list(range(n_up)),
            doubled=None, timer_s=cfg.timer_s, balance_before=self.balance,
        )
        # the doubled item must stay hidden, so never flip the last hidden item under double_hidden
        if cfg.mid_round_flip and k >= (2 if event == DOUBLE_HIDDEN else 1):
            rnd.flip_at = rng.uniform(0.3, 0.6) * cfg.timer_s
            rnd.flip_index = rng.choice(hidden)
            rnd.flip_stale = cfg.stale_quotes and rng.random() < 0.5
            rnd.flip_noise = rng.gauss(0, cfg.quote_noise_sd)
        if event == DOUBLE_HIDDEN:
            rnd.doubled = rng.choice([i for i in hidden if i != rnd.flip_index])
        m = rnd.market()
        bid, ask = make_quote(m.fair, rng.gauss(0, cfg.quote_noise_sd), cfg.spread, cfg.TICK)
        rnd.tape.append((0.0, bid, ask))
        if max(risk_limits(self.balance, bid, ask, m.settle_min, m.settle_max)) < 1:
            self.out_of_risk = True
            return None
        self.rounds.append(rnd)
        return rnd

    def advance(self, t: float) -> bool:
        """Move the open round's clock to `t` seconds; returns True if an item flipped just now."""
        rnd = self.current
        if rnd is None or rnd.decision is not None or rnd.flip_at is None or rnd.flipped_at is not None:
            return False
        if t < rnd.flip_at:
            return False
        rnd.face_up.append(rnd.flip_index)
        rnd.flipped_at = rnd.flip_at
        if not rnd.flip_stale:
            bid, ask = make_quote(rnd.market().fair, rnd.flip_noise, self.config.spread, self.config.TICK)
            rnd.tape.append((rnd.flip_at, bid, ask))
        return True

    def limits(self) -> tuple[int, int]:
        rnd = self._open_round()
        m = rnd.market()
        return risk_limits(self.balance, rnd.bid, rnd.ask, m.settle_min, m.settle_max)

    def buy(self, size: int, t: float) -> Round:
        return self._decide(BUY, size, t)

    def sell(self, size: int, t: float) -> Round:
        return self._decide(SELL, size, t)

    def pass_(self, t: float) -> Round:
        return self._decide(PASS, 0, t)

    def timeout(self) -> Round:
        return self._decide(TIMEOUT, 0, float(self.config.timer_s))

    def report(self, value: Any, answer_time: float) -> bool:
        """Record the player's P&L report (int, Decimal or text). Correct = equal after rounding to cents."""
        rnd = self.current
        if rnd is None or rnd.decision is None:
            raise RuntimeError("nothing to report yet")
        if rnd.reported is not None:
            raise RuntimeError("P&L already reported")
        to_cents(value)  # reject non-numbers before recording anything
        rnd.reported = Decimal(str(value).strip())
        rnd.answer_time = answer_time
        return bool(rnd.report_correct)

    def _open_round(self) -> Round:
        rnd = self.current
        if rnd is None or rnd.decision is not None:
            raise RuntimeError("no open round")
        return rnd

    def _decide(self, action: str, size: int, t: float) -> Round:
        rnd = self._open_round()
        t = min(max(t, 0.0), float(self.config.timer_s))
        self.advance(t)
        max_long, max_short = self.limits()
        if action in (BUY, SELL):
            cap = max_long if action == BUY else max_short
            if self.config.sizing == "fixed" and size != 1:
                raise ValueError("fixed sizing trades exactly 1 unit")
            if not 1 <= size <= cap:
                raise ValueError(f"size {size} outside allowed 1–{cap}")
        else:
            size = 0
        rnd.decision = Decision(action, size, t, rnd.bid, rnd.ask, rnd.market(), max_long, max_short)
        self.balance += rnd.pnl
        rnd.balance_after = self.balance
        return rnd
