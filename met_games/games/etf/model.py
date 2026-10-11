"""ETF Arb market model: the basket, the price path, events, ETF quotes, NAV, and P&L math.

Pure Python, no UI imports. All money and prices are Decimal. Each difficulty has one price tick — whole
dollars (EASY), tenths (MEDIUM) or cents (HARD) — and everything priced uses it: the stock prices, each row's
W × P (weight × price, rounded to the tick), NAV = the sum of those W × P values, and the ETF quote.

Everything about the market is drawn up front from the setup RNG, round by round, so the same
seed gives the same basket, prices, events and quotes whatever anyone does.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, Inexact, localcontext

from met_games.games.etf.config import EtfConfig

D = Decimal
CENT = D("0.01")
TICKERS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "XOM", "JNJ", "WMT", "PG", "MA", "HD", "KO")
MIN_SPREAD = D("0.20")  # ask − bid: 0.20, or one tick when the tick is bigger (EASY: $1)
MOVE_SD = 0.006  # price move sd, as a share of price
STILL_P = 0.2  # chance a stock doesn't move in a round
SPLIT, REVERSE, REBAL = "split", "reverse", "rebalance"
BUY, SELL, SKIP = "BUY", "SELL", "SKIP"


def to_tick(x: Decimal, tick: Decimal) -> Decimal:
    return x.quantize(tick, rounding=ROUND_HALF_UP)


def round_cents(x: Decimal) -> Decimal:
    return to_tick(x, CENT)


def spread(tick: Decimal) -> Decimal:
    return max(MIN_SPREAD, tick)


def fmt_px(x: Decimal, tick: Decimal) -> str:
    """A price-like number at the tick's precision: 128 / 128.1 / 128.14."""
    places = max(0, -tick.as_tuple().exponent)
    return f"{to_tick(x, tick):,.{places}f}"


def wxp(weight: Decimal, price: Decimal, tick: Decimal) -> Decimal:
    """One row's W × P, rounded to the price tick."""
    return to_tick(weight * price, tick)


def exact_div(x: Decimal, k: int) -> Decimal | None:
    """x / k if that is an exact (finite) decimal, else None."""
    with localcontext() as ctx:
        ctx.traps[Inexact] = True
        try:
            return (x / k).normalize()
        except Inexact:
            return None


def fmt_weight(w: Decimal) -> str:
    """0.30 → "0.3", 0.15 → "0.15", 0.6 → "0.6"; at least one decimal."""
    s = format(w.normalize(), "f")
    return s if "." in s else s + ".0"


# ── basket ───────────────────────────────────────────────────────────────────


def draw_weights(rng: random.Random, n: int, places: int, minimum: Decimal) -> list[Decimal]:
    """n weights on a 10^−places grid, each ≥ minimum, summing to exactly 1 (a uniform composition)."""
    unit = D(1).scaleb(-places)
    total, low = int(1 / unit), int(minimum / unit)
    spare = total - n * low
    cuts = sorted(rng.sample(range(spare + n - 1), n - 1))
    parts, prev = [], -1
    for c in cuts + [spare + n - 1]:
        parts.append(c - prev - 1)
        prev = c
    return [(low + p) * unit for p in parts]


def start_price(rng: random.Random, tick: Decimal) -> Decimal:
    """Uniform over the tick grid in 50–600."""
    steps = int(1 / tick)
    return D(rng.randint(50 * steps, 600 * steps)) * tick


def move(rng: random.Random, price: Decimal, tick: Decimal) -> Decimal:
    """One round's move: still with probability STILL_P, else a normal draw with sd 0.6% of price."""
    if rng.random() < STILL_P:
        return price
    return to_tick(price + D(str(round(rng.gauss(0, MOVE_SD * float(price)), 6))), tick)


@dataclass(frozen=True)
class Event:
    ticker: str
    kind: str  # SPLIT / REVERSE / REBAL
    ratio: int = 1  # N for splits
    old_weight: Decimal = D(0)  # the weight the table shows
    new_weight: Decimal = D(0)  # the weight NAV actually uses this round

    @property
    def banner(self) -> str:
        old = fmt_weight(self.old_weight)
        if self.kind == SPLIT:
            return (f"⚑ {self.ticker} {self.ratio}-for-1 SPLIT — price is post-split; the table still shows the OLD "
                    f"weight {old} (× {self.ratio})")
        if self.kind == REVERSE:
            return (f"⚑ {self.ticker} 1-for-{self.ratio} REVERSE SPLIT — price is post-split; the table still shows "
                    f"the OLD weight {old} (÷ {self.ratio})")
        return (f"⚑ {self.ticker} REBALANCE — weight {old} → {fmt_weight(self.new_weight)}; the table still "
                f"shows {old}")

    @property
    def chg_label(self) -> str:
        return "rebal" if self.kind == REBAL else "split"


@dataclass(frozen=True)
class RoundPlan:
    """Everything about one round's market, drawn at setup."""

    number: int
    tickers: tuple[str, ...]
    prev_prices: tuple[Decimal, ...]
    prices: tuple[Decimal, ...]  # shown (post-split on an event round)
    shown_weights: tuple[Decimal, ...]  # what the table shows
    weights: tuple[Decimal, ...]  # what NAV uses (the event applied)
    event: Event | None
    gap: Decimal  # NAV − mid: positive = the ETF is cheap
    bid: Decimal
    ask: Decimal
    tick: Decimal = CENT  # the difficulty's price precision

    @property
    def nav(self) -> Decimal:
        return nav(self.weights, self.prices, self.tick)

    @property
    def naive_nav(self) -> Decimal:
        """NAV with the table's weights: what you get if you ignore the event (the trap)."""
        return nav(self.shown_weights, self.prices, self.tick)

    def row(self, ticker: str) -> int:
        return self.tickers.index(ticker)

    def wxp_change(self, i: int, adjusted: bool = False) -> Decimal:
        """How much row i's W × P moved since last round: this round's W × P minus last round's. Last round's
        weight is the one the table shows now, so last NAV + Σ wxp_change = this round's Σ W × P exactly (the
        table's sum; with `adjusted`, the event-adjusted NAV)."""
        now = self.weights[i] if adjusted else self.shown_weights[i]
        return wxp(now, self.prices[i], self.tick) - wxp(self.shown_weights[i], self.prev_prices[i], self.tick)


def nav(weights: tuple[Decimal, ...] | list[Decimal], prices: tuple[Decimal, ...] | list[Decimal],
        tick: Decimal) -> Decimal:
    """Σ of each row's W × P rounded to the tick — exactly the column the player adds up."""
    return sum((wxp(w, p, tick) for w, p in zip(weights, prices)), D(0))


def draw_gap(rng: random.Random, cfg: EtfConfig) -> Decimal:
    """|g| uniform over cents 0.00–0.45 with probability skip_chance (a skip round), else gap_min–gap_max;
    sign 50/50."""
    if rng.random() < cfg.skip_chance:
        size = rng.randint(0, 45)
    else:
        size = rng.randint(int(cfg.gap_min * 100), int(cfg.gap_max * 100))
    return D(size) * CENT * (1 if rng.random() < 0.5 else -1)


def quote(nav_value: Decimal, gap: Decimal, tick: Decimal = CENT) -> tuple[Decimal, Decimal]:
    """bid = (mid − spread/2) rounded to the tick, ask = bid + spread; mid = NAV − gap."""
    s = spread(tick)
    bid = to_tick(nav_value - gap - s / 2, tick)
    return bid, to_tick(bid + s, tick)


def draw_event(rng: random.Random, cfg: EtfConfig, tickers: tuple[str, ...], weights: list[Decimal]) -> Event:
    i = rng.randrange(len(tickers))
    kind = rng.choice((SPLIT, REVERSE, REBAL))
    w = weights[i]
    if kind == SPLIT:
        n = rng.choice((2, 3))
        return Event(tickers[i], SPLIT, n, w, w * n)
    if kind == REVERSE:
        n = rng.choice([k for k in (2, 3) if exact_div(w, k) is not None])  # exact only; ÷2 always is
        return Event(tickers[i], REVERSE, n, w, exact_div(w, n))
    step = D("0.1") if cfg.weight_places == 1 else D("0.05")
    k = rng.choice([k for k in (-2, -1, 1, 2) if w + k * step >= cfg.min_weight])
    return Event(tickers[i], REBAL, 1, w, w + k * step)


@dataclass(frozen=True)
class Market:
    tickers: tuple[str, ...]
    start_weights: tuple[Decimal, ...]
    start_prices: tuple[Decimal, ...]
    rounds: tuple[RoundPlan, ...]

    def nav_before(self, number: int) -> Decimal:
        """The NAV going into round `number`: last round's NAV, or the opening NAV before round 1."""
        if number == 1:
            return nav(self.start_weights, self.start_prices, self.rounds[0].tick)
        return self.rounds[number - 2].nav


def draw_market(cfg: EtfConfig, rng: random.Random) -> Market:
    """Draw order: tickers, weights, start prices; then per round: every stock's move, the event coin
    (and its stock, kind, ratio / new weight), the gap."""
    tick = cfg.price_tick
    tickers = tuple(rng.sample(TICKERS, cfg.stocks))
    weights = draw_weights(rng, cfg.stocks, cfg.weight_places, cfg.min_weight)
    prices = [start_price(rng, tick) for _ in tickers]
    start = (tuple(weights), tuple(prices))
    plans = []
    for r in range(1, cfg.rounds + 1):
        prev = tuple(prices)
        prices = [move(rng, p, tick) for p in prices]
        shown = tuple(weights)
        event = None
        if cfg.events and rng.random() < cfg.event_freq:
            event = draw_event(rng, cfg, tickers, weights)
            i = tickers.index(event.ticker)
            if event.kind == SPLIT:
                prices[i] = to_tick(prices[i] / event.ratio, tick)
            elif event.kind == REVERSE:
                prices[i] = prices[i] * event.ratio
            weights[i] = event.new_weight  # carries forward: later rounds show it
        gap = draw_gap(rng, cfg)
        bid, ask = quote(nav(weights, prices, tick), gap, tick)
        plans.append(RoundPlan(r, tickers, prev, tuple(prices), shown, tuple(weights), event, gap, bid, ask, tick))
    return Market(tickers, start[0], start[1], tuple(plans))


# ── trade math ───────────────────────────────────────────────────────────────


def gross(side: str, units: int, nav_value: Decimal, bid: Decimal, ask: Decimal) -> Decimal:
    """Buy: (NAV − ask) × units. Sell: (bid − NAV) × units."""
    return (nav_value - ask) * units if side == BUY else (bid - nav_value) * units


def bonus(first: bool, gross_value: Decimal, fee: Decimal, rate: Decimal) -> Decimal:
    """The first trade of the round earns rate × (gross − fee), only if that is positive."""
    base = gross_value - fee
    return base * rate if first and base > 0 else D(0)


def right_call(nav_value: Decimal, bid: Decimal, ask: Decimal, units: int, fee: Decimal) -> tuple[str, Decimal]:
    """(BUY / SELL / SKIP, per-unit edge of that side). u = min(max units, size at that side at round start):
    BUY if (NAV − ask) × u > fee, SELL if (bid − NAV) × u > fee, else SKIP (edge = the better side's)."""
    buy_edge, sell_edge = nav_value - ask, bid - nav_value
    if buy_edge * units > fee:
        return BUY, buy_edge
    if sell_edge * units > fee:
        return SELL, sell_edge
    return SKIP, max(buy_edge, sell_edge)
