"""Dice event display modes: high_only draws the value (5 or 6 pips); remap events draw the rolled face."""

import pytest
from textual.app import App, ComposeResult

from mtt_games.__main__ import build_app, parse_args
from mtt_games.games.dice.config import HARD
from mtt_games.games.dice.engine import DICE, DiceSession, Die
from mtt_games.games.dice.ui import DieWidget, die_widget
from mtt_games.games.sumgame.screens.reveal import RevealScreen
from mtt_games.games.sumgame.screens.round import RoundScreen


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTT_GAMES_HOME", str(tmp_path))


def pips(w: DieWidget) -> int:
    return w.content.plain.count("●")


def struck(w: DieWidget) -> bool:
    return any("strike" in str(span.style) for span in w.content.spans)


class DiceRow(App):
    def __init__(self, event: str) -> None:
        super().__init__()
        self.event = event

    def compose(self) -> ComposeResult:
        for face in range(1, 7):
            die = Die(face)
            yield die_widget(die, DICE.value(die, self.event), True, self.event)


async def test_high_only_die_never_renders_one_to_four_pips():
    app = DiceRow("high_only")
    async with app.run_test() as pilot:
        await pilot.pause()
        widgets = list(app.query(DieWidget))
        assert len(widgets) == 6  # every possible roll, 1..6
        for w in widgets:
            assert pips(w) in (5, 6)
            assert pips(w) == w.value  # the face shown is the value counted
            assert not struck(w)
            assert f"={w.value}" in w.content.plain


async def test_remap_events_still_show_rolled_face_struck_through():
    app = DiceRow("one_is_seven")
    async with app.run_test() as pilot:
        await pilot.pause()
        one = list(app.query(DieWidget))[0]  # rolled 1, worth 7
        assert pips(one) == 1 and struck(one) and "1=7" in one.content.plain


def high_only_seed() -> int:
    """A seed whose first HARD dice round is high_only (found via the engine, so the test stays exact)."""
    return next(s for s in range(1, 500) if DiceSession(HARD.replace(seed=s)).new_round().event == "high_only")


async def test_high_only_round_and_reveal_show_only_fives_and_sixes():
    seed = high_only_seed()
    app = build_app(parse_args(["dice", "--seed", str(seed)]))
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.press("down", "down", "enter")  # HARD
        await pilot.pause()
        assert isinstance(app.screen, RoundScreen) and app.screen.rnd.event == "high_only"
        shown = [w for w in app.screen.item_widgets if w.face_up]
        assert shown and all(pips(w) in (5, 6) and not struck(w) for w in shown)
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, RevealScreen)
        revealed = list(app.screen.query(DieWidget))
        assert revealed and all(pips(w) in (5, 6) and not struck(w) for w in revealed)
