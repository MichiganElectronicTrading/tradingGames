"""Card Game UI spec: banner, card widget, rules text."""

from __future__ import annotations

from mtt_games.games.card.deck import Card
from mtt_games.games.card.engine import CardSession
from mtt_games.games.sumgame.ui import GameUI, register
from mtt_games.widgets import CardWidget

BANNER = """\
 ██████  █████  ██████  ██████
██      ██   ██ ██   ██ ██   ██
██      ███████ ██████  ██   ██
██      ██   ██ ██   ██ ██   ██
 ██████ ██   ██ ██   ██ ██████"""


def card_widget(card: Card, value: int, face_up: bool, event: str | None) -> CardWidget:
    return CardWidget(card.label, card.suit, card.rank, value, face_up=face_up, red=card.is_red)


CARD_UI = register(GameUI(
    session_cls=CardSession,
    banner=BANNER,
    tagline="market-taking drill",
    make_widget=card_widget,
    setup_rules=(
        "Each round a fresh 52-card deck is shuffled and a few cards are dealt. 2–10 count face value, "
        "J=11, Q=12, K=13, A=14. Some cards are dealt face up; the rest stay hidden.",
        "The round settles at the sum of ALL dealt cards (after any market event).",
    ),
    fair_rules=(
        "Hidden cards are a uniform draw from every card you can't see, so:",
        "fair = face-up sum + hidden count × mean of the cards not face up.",
    ),
))
