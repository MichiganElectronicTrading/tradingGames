"""Config shared by every sum game. Each game subclasses SumConfig, names its item-count fields,
and sets its tick size, price display and event list."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

SIZINGS = ("fixed", "choose")
EVENT_FREQS = (0.0, 1 / 3, 1.0)
NEXT_MODE = {"EASY": "MEDIUM", "MEDIUM": "HARD", "HARD": "HARD", "CUSTOM": "EASY"}


@dataclass(frozen=True)
class SumConfig:
    NOUN: ClassVar[str] = "items"  # plural item name: "cards", "dice"
    COUNT_FIELDS: ClassVar[tuple[str, str]] = ("n_min", "n_max")  # the subclass's item-count field names
    TICK: ClassVar[int | Decimal] = 1  # price increment; spreads are whole numbers of ticks
    PRICE_PLACES: ClassVar[int] = 0  # decimals when showing prices and money
    SPREAD_MAX: ClassVar[int | Decimal] = 8
    EVENT_KEYS: ClassVar[tuple[str, ...]] = ()

    face_up_min: int = 0
    face_up_max: int = 1
    rounds: int = 4
    timer_s: int = 60
    budget: int = 500
    spread: int | Decimal = 4
    quote_noise_sd: float = 3.0
    sizing: str = "fixed"
    mid_round_flip: bool = False
    stale_quotes: bool = False
    event_freq: float = 0.0
    enabled_events: tuple[str, ...] = ()
    seed: int | None = None

    @property
    def n_min(self) -> int:
        return getattr(self, self.COUNT_FIELDS[0])

    @property
    def n_max(self) -> int:
        return getattr(self, self.COUNT_FIELDS[1])

    @classmethod
    def price(cls, x: Any) -> str:
        return f"{x:.{cls.PRICE_PLACES}f}"

    def errors(self) -> list[str]:
        """Every validation problem with this config (empty list = valid)."""
        noun = self.NOUN
        errs: list[str] = []
        if not (2 <= self.n_min <= 10 and 2 <= self.n_max <= 10):
            errs.append(f"{noun} must be 2–10")
        if self.n_min > self.n_max:
            errs.append(f"{noun} min > {noun} max")
        if self.face_up_min < 0:
            errs.append("face-up min must be ≥ 0")
        if self.face_up_min > self.face_up_max:
            errs.append("face-up min > face-up max")
        if self.face_up_max > self.n_min:
            errs.append(f"face-up max must be ≤ {noun} min")
        if not 1 <= self.rounds <= 20:
            errs.append("rounds must be 1–20")
        if not 5 <= self.timer_s <= 120:
            errs.append("timer must be 5–120s")
        if not self._spread_ok():
            ticks = "" if self.TICK == 1 else f" in {self.price(self.TICK)} ticks"
            errs.append(f"spread must be {self.price(self.TICK)}–{self.price(self.SPREAD_MAX)}{ticks}")
        if self.budget <= 0:
            errs.append("budget must be > 0")
        if self.quote_noise_sd < 0:
            errs.append("quote noise must be ≥ 0")
        if self.sizing not in SIZINGS:
            errs.append("sizing must be fixed or choose")
        if self.stale_quotes and not self.mid_round_flip:
            errs.append("stale quotes need mid-round flip")
        if not any(math.isclose(self.event_freq, f) for f in EVENT_FREQS):
            errs.append("event freq must be 0, 1/3 or 1")
        unknown = [e for e in self.enabled_events if e not in self.EVENT_KEYS]
        if unknown:
            errs.append(f"unknown event: {unknown[0]}")
        if self.event_freq > 0 and not self.enabled_events:
            errs.append("events on but none enabled")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            errs.append("seed must be an integer or empty")
        return errs

    def _spread_ok(self) -> bool:
        try:
            spread, tick = Decimal(str(self.spread)), Decimal(str(self.TICK))
        except InvalidOperation:
            return False
        return tick <= spread <= Decimal(str(self.SPREAD_MAX)) and spread % tick == 0

    def validate(self) -> None:
        errs = self.errors()
        if errs:
            raise ValueError("; ".join(errs))

    def replace(self, **changes: Any) -> SumConfig:
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["enabled_events"] = list(self.enabled_events)
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in d.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SumConfig:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        if "enabled_events" in kwargs:
            kwargs["enabled_events"] = tuple(kwargs["enabled_events"])
        if "spread" in kwargs and isinstance(cls.TICK, Decimal):
            kwargs["spread"] = Decimal(str(kwargs["spread"]))
        return cls(**kwargs)


def span(lo: int, hi: int) -> str:
    return str(lo) if lo == hi else f"{lo}–{hi}"


def freq_label(freq: float) -> str:
    if math.isclose(freq, 0):
        return "off"
    if math.isclose(freq, 1):
        return "every round"
    return "1/3 of rounds"


def noise_label(cfg: SumConfig | type[SumConfig], sd: float) -> str:
    return f"{sd:.{max(1, cfg.PRICE_PLACES)}f}"


def events_label(cfg: SumConfig) -> str:
    if cfg.event_freq == 0:
        return "off"
    which = "all enabled" if set(cfg.enabled_events) == set(cfg.EVENT_KEYS) else f"{len(cfg.enabled_events)} enabled"
    return f"{freq_label(cfg.event_freq)}, {which}"


def describe(cfg: SumConfig) -> dict[str, str]:
    """Human-readable summary rows (used by the lobby's MODES table). A config subclass can
    supply its own rows by overriding `summary()`."""
    summary = getattr(cfg, "summary", None)
    if summary is not None:
        return summary()
    return {
        cfg.NOUN: span(cfg.n_min, cfg.n_max),
        "face up": span(cfg.face_up_min, cfg.face_up_max),
        "rounds": str(cfg.rounds),
        "timer": f"{cfg.timer_s}s",
        "spread": cfg.price(cfg.spread),
        "quote noise sd": noise_label(cfg, cfg.quote_noise_sd),
        "sizing": "fixed 1" if cfg.sizing == "fixed" else "choose",
        "mid-round flip": "on" if cfg.mid_round_flip else "off",
        "stale quotes": "on" if cfg.stale_quotes else "off",
        "events": events_label(cfg),
        "budget": f"${cfg.budget}",
    }
