"""ETF Arb configuration: EtfConfig and the EASY/MEDIUM/HARD presets. Money fields are Decimal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

D = Decimal
EVENT_FREQS = (0.25, 1 / 3, 0.5, 1.0)
DECIMAL_FIELDS = ("trader_sd", "fee", "bonus", "gap_min", "gap_max")


def freq_label(f: float) -> str:
    return {0.25: "~1 in 4", 0.5: "~1 in 2", 1.0: "every"}.get(f, "~1 in 3")


@dataclass(frozen=True)
class EtfConfig:
    budget: ClassVar[None] = None  # no bankroll: the shared lobby/custom top bars show no balance

    stocks: int = 4
    weight_places: int = 1  # 1 = whole tenths (each ≥ 0.1), 2 = hundredths (each ≥ 0.05)
    price_places: int = 0  # 0 = whole dollars, 1 = tenths, 2 = cents
    rounds: int = 6
    timer_s: int = 25
    size: int = 40  # units at the bid and at the ask, shared by everyone
    skip_chance: float = 0.15  # chance a round's gap is small (0.00–0.45): a deliberate skip round
    gap_min: Decimal = D("1.20")  # otherwise |gap| is uniform in gap_min–gap_max
    gap_max: Decimal = D("3.50")
    trader_sd: Decimal = D("1.00")  # computer traders' NAV error sd, $
    decide_min: float = 11.0  # computer decision time window, s
    decide_max: float = 20.0
    events: bool = False
    event_freq: float = 1 / 3  # chance of an event per round when events are on
    trap_skill: float = 0.7  # chance a computer trader applies an event correctly
    fee: Decimal = D("10")  # per trade
    bonus: Decimal = D("0.20")  # first trade of the round: + this share of (gross − fee), if positive
    max_units: int = 20
    seed: int | None = None

    @property
    def weight_unit(self) -> Decimal:
        return D(1).scaleb(-self.weight_places)

    @property
    def min_weight(self) -> Decimal:
        return D("0.1") if self.weight_places == 1 else D("0.05")

    @property
    def price_tick(self) -> Decimal:
        return D(1).scaleb(-self.price_places)

    def errors(self) -> list[str]:
        errs: list[str] = []
        if self.weight_places not in (1, 2):
            errs.append("weights must be tenths or hundredths")
        elif not 2 <= self.stocks <= min(10, int(1 / self.min_weight)):
            errs.append(f"stocks must be 2–{min(10, int(1 / self.min_weight))}")
        if self.price_places not in (0, 1, 2):
            errs.append("prices must be whole, tenths or cents")
        if not 1 <= self.rounds <= 20:
            errs.append("rounds must be 1–20")
        if not 3 <= self.timer_s <= 120:
            errs.append("timer must be 3–120s")
        if not 1 <= self.size <= 200:
            errs.append("size must be 1–200")
        if not 0 <= self.skip_chance <= 1:
            errs.append("skip-round chance must be 0–100%")
        if not D("0.46") <= self.gap_min <= self.gap_max <= D(10) or (self.gap_min * 100) % 1 or (self.gap_max * 100) % 1:
            errs.append("trade gap must be 0.46–10.00 in cents, min ≤ max")
        if not D(0) <= self.trader_sd <= D(10):
            errs.append("trader error sd must be 0–10")
        if not 0 <= self.decide_min <= self.decide_max <= 120:
            errs.append("decision time must be 0–120s with min ≤ max")
        if not 0 < self.event_freq <= 1:
            errs.append("event frequency must be in (0, 1]")
        if not 0 <= self.trap_skill <= 1:
            errs.append("trader event skill must be 0–1")
        if self.fee < 0:
            errs.append("fee must be ≥ 0")
        if not D(0) <= self.bonus <= D(1):
            errs.append("bonus must be 0–100%")
        if not 1 <= self.max_units <= 100:
            errs.append("max units must be 1–100")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            errs.append("seed must be an integer or empty")
        return errs

    def validate(self) -> None:
        errs = self.errors()
        if errs:
            raise ValueError("; ".join(errs))

    def replace(self, **changes: Any) -> EtfConfig:
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EtfConfig:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        try:
            for k in DECIMAL_FIELDS:
                if k in kwargs:
                    kwargs[k] = D(str(kwargs[k]))
        except InvalidOperation:
            raise ValueError("bad number in preset") from None
        return cls(**kwargs)

    def summary(self) -> dict[str, str]:
        """Rows for the lobby's MODES table."""
        places = {1: "tenths", 2: "hundredths"}
        prices = {0: "whole", 1: "tenths", 2: "cents"}
        return {
            "stocks": str(self.stocks),
            "weights / prices": f"{places.get(self.weight_places, '?')} / {prices.get(self.price_places, '?')}",
            "rounds · timer": f"{self.rounds} · {self.timer_s}s",
            "size at bid / ask": str(self.size),
            "skip-round chance · trade gap": f"{self.skip_chance:.0%} · {self.gap_min:.2f}–{self.gap_max:.2f}",
            "trader error sd · decision time": f"{self.trader_sd:.2f} · {self.decide_min:g}–{self.decide_max:g}s",
            "events": f"{freq_label(self.event_freq)} rounds" if self.events else "off",
            "fee · bonus · units": f"${self.fee:g} · {self.bonus * 100:g}% · 1–{self.max_units}",
        }


EASY = EtfConfig()
MEDIUM = EtfConfig(
    stocks=5, weight_places=2, price_places=1, rounds=6, timer_s=20, size=30, skip_chance=0.22, gap_min=D("0.70"),
    gap_max=D("3.00"), trader_sd=D("0.30"),
    decide_min=7.0, decide_max=14.0,
)
HARD = EtfConfig(
    stocks=6, weight_places=2, price_places=2, rounds=8, timer_s=10, size=20, skip_chance=0.25, gap_min=D("0.55"),
    gap_max=D("3.00"), trader_sd=D("0.10"),
    decide_min=2.0, decide_max=7.0, events=True,
)

PRESETS: dict[str, EtfConfig] = {"EASY": EASY, "MEDIUM": MEDIUM, "HARD": HARD}
