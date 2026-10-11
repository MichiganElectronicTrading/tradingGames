"""Higher or Lower configuration: HiloConfig and the EASY/MEDIUM/HARD presets."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any, ClassVar

INTERVIEW, FULL, REDBLACK = "interview", "full", "redblack"
DECKS = (INTERVIEW, FULL, REDBLACK)
DECK_LABELS = {INTERVIEW: "Interview", FULL: "Full", REDBLACK: "Red/Black"}
ODDS, COUNTS, MINIMAL = "odds", "counts", "minimal"  # board levels
BOARDS = (ODDS, COUNTS, MINIMAL)
BOARD_LABELS = {
    ODDS: "counts + lower/same/higher + odds",
    COUNTS: "counts + lower/same/higher",
    MINIMAL: "cards left + last three",
}


@dataclass(frozen=True)
class HiloConfig:
    budget: ClassVar[None] = None  # no bankroll in the shared top bars

    deck: str = INTERVIEW
    timed: bool = False  # off: no bet clock, no timeouts, no speed multipliers
    time_s: int = 10  # time per bet, when timed
    board: str = ODDS
    start_capital: int = 1000
    quick_lock: bool = True  # a stake key locks the bet once a side is chosen
    seed: int | None = None

    def errors(self) -> list[str]:
        errs: list[str] = []
        if self.deck not in DECKS:
            errs.append("deck must be interview, full or redblack")
        if not 2 <= self.time_s <= 30:
            errs.append("time per bet must be 2–30s")
        if self.board not in BOARDS:
            errs.append("board must be odds, counts or minimal")
        if not 100 <= self.start_capital <= 1_000_000:
            errs.append("start capital must be 100–1,000,000")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            errs.append("seed must be an integer or empty")
        return errs

    def validate(self) -> None:
        errs = self.errors()
        if errs:
            raise ValueError("; ".join(errs))

    def replace(self, **changes: Any) -> HiloConfig:
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HiloConfig:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def summary(self) -> dict[str, str]:
        """Rows for the lobby's MODES table."""
        return {
            "default deck": DECK_LABELS.get(self.deck, self.deck),
            "time per bet": f"{self.time_s}s" if self.timed else "untimed",
            "board shows": BOARD_LABELS.get(self.board, self.board),
            "start capital": f"{self.start_capital:,}",
        }


EASY = HiloConfig()
MEDIUM = HiloConfig(deck=FULL, board=COUNTS)
HARD = HiloConfig(deck=FULL, board=MINIMAL)

PRESETS: dict[str, HiloConfig] = {"EASY": EASY, "MEDIUM": MEDIUM, "HARD": HARD}
