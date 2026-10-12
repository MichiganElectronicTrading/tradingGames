"""The outcry command line: parse what the player typed into a Command. Pure Python.

    b 464        bid 464              buy / sell   lift the best offer / hit the best bid
    o 467        offer 467            x            cancel all
    464 @ 467    bid and offer        xb / xo      cancel your bid / your offer
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BID_CMD, OFFER_CMD, BOTH, LIFT, HIT, CANCEL_ALL, CANCEL_BID, CANCEL_OFFER = (
    "bid", "offer", "both", "buy", "sell", "x", "xb", "xo",
)
MAX_PRICE = 9999
CHEAT_SHEET = "b 464 bid · o 467 offer · 464 @ 467 both · buy · sell · x cancel all · xb / xo · ↑ recall · ^B ^S · ^X cancel all"
_SIMPLE = {"buy": LIFT, "sell": HIT, "x": CANCEL_ALL, "xb": CANCEL_BID, "xo": CANCEL_OFFER}
_ONE_SIDE = re.compile(r"^([bo])\s*(\S+)$")
_TWO_SIDES = re.compile(r"^(\S+)\s*@\s*(\S+)$")


class CommandError(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    kind: str
    bid: int | None = None
    ask: int | None = None


def _price(text: str) -> int:
    if not re.fullmatch(r"\d+", text):
        raise CommandError(f"'{text}' is not a price — prices are whole numbers")
    price = int(text)
    if price > MAX_PRICE:
        raise CommandError(f"{price} is too high (max {MAX_PRICE})")
    return price


def parse_command(text: str) -> Command:
    t = " ".join(text.strip().lower().split())
    if not t:
        raise CommandError("type a command — e.g. b 464, o 467, 464 @ 467, buy, sell, x")
    if t in _SIMPLE:
        return Command(_SIMPLE[t])
    m = _ONE_SIDE.match(t)
    if m:
        price = _price(m.group(2))
        return Command(BID_CMD, bid=price) if m.group(1) == "b" else Command(OFFER_CMD, ask=price)
    m = _TWO_SIDES.match(t)
    if m:
        bid, ask = _price(m.group(1)), _price(m.group(2))
        if bid >= ask:
            raise CommandError(f"bid {bid} must be below offer {ask}")
        return Command(BOTH, bid=bid, ask=ask)
    raise CommandError(f"unknown command '{text.strip()}' — try b 464, o 467, 464 @ 467, buy, sell, x")
