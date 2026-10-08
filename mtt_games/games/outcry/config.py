"""Outcry configuration: OutcryConfig and the EASY/MEDIUM/HARD presets."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any, ClassVar

MAKER, SNIPER, PASSIVE, CHASER, ANCHOR = "MAKER", "SNIPER", "PASSIVE", "CHASER", "ANCHOR"
STYLES = (MAKER, SNIPER, PASSIVE, CHASER, ANCHOR)
STYLE_FIELDS = ("makers", "snipers", "passives", "chasers", "anchors")  # config field per style, same order

PACE_STEP = 0.25  # the tick: the pace cap is a whole number of ticks
HELPERS = ("fair", "range", "off")
HELPER_LABELS = {"fair": "range seen + exact fair", "range": "range seen only", "off": "off"}

PLAYER = "YOU"
TRADER_NAMES = ("ATLAS", "BOREAS", "CASSIA", "DRACO", "ECHO", "FENRIR", "GAIA", "HELIOS", "IRIS")


@dataclass(frozen=True)
class OutcryConfig:
    budget: ClassVar[None] = None  # no bankroll: the shared lobby/custom top bars show no balance

    players: int = 8
    rounds: int = 7
    respond_s: int = 15  # respond / open timer
    outcry_s: int = 30
    report_s: int = 30  # trade-score report timer
    trade_size: int = 1
    limit: int = 10  # position limit, ±
    helper: str = "fair"
    makers: int = 1
    snipers: int = 0
    passives: int = 3
    chasers: int = 0
    anchors: int = 3
    cooldown_min: float = 6.0  # each trader's cooldown between actions, s
    cooldown_max: float = 10.0
    pace_s: float = 1.5  # table-wide cap: at most one computer action per this many seconds
    learns: bool = False  # traders shift their estimate toward each trade price
    extreme_reveals: bool = True  # lowest/highest revealed on a fixed schedule
    seed: int | None = None

    @property
    def names(self) -> tuple[str, ...]:
        """Seat names in display order: you, then the computer traders."""
        return (PLAYER, *TRADER_NAMES[: self.players - 1])

    @property
    def style_counts(self) -> tuple[int, ...]:
        return tuple(getattr(self, f) for f in STYLE_FIELDS)

    def style_list(self) -> list[str]:
        return [s for s, n in zip(STYLES, self.style_counts) for _ in range(n)]

    @property
    def cooldown(self) -> tuple[float, float]:
        return self.cooldown_min, self.cooldown_max

    def errors(self) -> list[str]:
        errs: list[str] = []
        if not 4 <= self.players <= 10:
            errs.append("players must be 4–10")
        if not 1 <= self.rounds <= self.players - 1:
            errs.append("rounds must be 1–(players − 1)")
        if self.extreme_reveals and self.rounds < 2:
            errs.append("extreme reveals need 2+ rounds")
        if not 3 <= self.respond_s <= 120:
            errs.append("respond timer must be 3–120s")
        if not 5 <= self.outcry_s <= 300:
            errs.append("outcry must be 5–300s")
        if not 10 <= self.report_s <= 300:
            errs.append("report timer must be 10–300s")
        if not 1 <= self.trade_size <= 5:
            errs.append("trade size must be 1–5")
        if not 10 <= self.limit <= 50:
            errs.append("limit must be 10–50")
        if self.helper not in HELPERS:
            errs.append("helper must be fair, range or off")
        if any(n < 0 for n in self.style_counts):
            errs.append("style counts must be ≥ 0")
        elif sum(self.style_counts) != self.players - 1:
            errs.append(f"styles must add up to {self.players - 1} traders")
        if not 0.5 <= self.cooldown_min <= self.cooldown_max <= 60:
            errs.append("trader cooldown must be 0.5–60s with min ≤ max")
        if not (PACE_STEP <= self.pace_s <= 10 and (self.pace_s / PACE_STEP).is_integer()):
            errs.append("pace cap must be 0.25–10s in 0.25s steps")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            errs.append("seed must be an integer or empty")
        return errs

    def validate(self) -> None:
        errs = self.errors()
        if errs:
            raise ValueError("; ".join(errs))

    def replace(self, **changes: Any) -> OutcryConfig:
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutcryConfig:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def summary(self) -> dict[str, str]:
        """Rows for the lobby's MODES table."""
        lo, hi = self.cooldown
        return {
            "players": str(self.players),
            "rounds": str(self.rounds),
            "respond / open timer": f"{self.respond_s}s",
            "outcry": f"{self.outcry_s}s",
            "trade size · limit": f"{self.trade_size} lot · ±{self.limit}",
            "helper panel": HELPER_LABELS.get(self.helper, self.helper),
            "styles": styles_label(self),
            "cooldown": f"{lo:g}–{hi:g}s",
            "pace cap": f"1 action / {self.pace_s:g}s",
            "learns from tape": "yes" if self.learns else "no",
        }


def styles_label(cfg: OutcryConfig) -> str:
    return ", ".join(f"{n} {s}" for s, n in zip(STYLES, cfg.style_counts) if n)


EASY = OutcryConfig()
MEDIUM = OutcryConfig(
    respond_s=10, outcry_s=20, helper="range", makers=2, snipers=2, passives=1, chasers=1,
    anchors=1, cooldown_min=3.0, cooldown_max=6.0, pace_s=0.75,
)
HARD = OutcryConfig(
    respond_s=5, outcry_s=15, helper="off", makers=3, snipers=2, passives=0, chasers=1, anchors=1,
    cooldown_min=1.0, cooldown_max=3.0, pace_s=0.25, learns=True,
)

PRESETS: dict[str, OutcryConfig] = {"EASY": EASY, "MEDIUM": MEDIUM, "HARD": HARD}
