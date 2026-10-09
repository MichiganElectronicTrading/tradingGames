"""ETF Arb Pilot tests, driven by a fake clock (`app.etf_clock`), so nothing waits on real time."""

import json
import random
from decimal import ROUND_HALF_UP, Decimal

import pytest
from textual.widgets import Static

from mtt_games.__main__ import build_app, parse_args
from mtt_games.app import MTTGamesApp
from mtt_games.games.etf.config import EASY, HARD, MEDIUM
from mtt_games.games.etf.engine import YOU, EtfGame
from mtt_games.games.etf.model import BUY, SELL, draw_market, nav
from mtt_games.games.etf.screens.common import basket_table
from mtt_games.games.etf.screens.recap import RecapScreen
from mtt_games.games.etf.screens.result import ResultScreen
from mtt_games.games.etf.screens.round import RoundScreen
from mtt_games.games.etf.stats import leaderboard
from mtt_games.games.sumgame.screens.lobby import LobbyScreen
from mtt_games.widgets import KeyButton

SIZE = (150, 50)


class FakeClock:
    def __init__(self) -> None:
        self.t = 500.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTT_GAMES_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def wait(pilot, clock: FakeClock, seconds: float) -> None:
    clock.t += seconds
    pilot.app.screen.sync()
    await pilot.pause()


async def test_full_easy_session_with_the_fake_clock(isolated_home):
    app = build_app(parse_args(["etf", "--seed", "7"]))
    clock = FakeClock()
    app.etf_clock = clock
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen) and app.screen.ui.source.key == "etf"
        await pilot.press("enter")  # EASY
        await pilot.pause()
        game = app.screen.game
        assert game.seed == 7 and game.mode == "EASY"
        script = ["b", "s", "k", "timeout", "k", "k"]
        for n, step in enumerate(script, start=1):
            screen = app.screen
            assert isinstance(screen, RoundScreen) and game.round.number == n
            last_column = [str(c) for c in screen.query_one("#basket", Static).content.columns[-1].cells]
            assert last_column[-1] == "Σ = ?"  # NAV is yours to work out
            await wait(pilot, clock, 1)
            if step == "timeout":
                await wait(pilot, clock, game.config.timer_s)
            else:
                if step in "bs":
                    await pilot.press("left", "left", "left", "left", "left")  # 20 → 15 units
                await pilot.press(step)
                await pilot.pause()
                mine = game.round.decisions[YOU]
                if step == "b":
                    assert mine.fill.side == BUY and mine.fill.units == 15
                elif step == "s":
                    assert mine.fill.side == SELL and mine.fill.units == 15
                else:
                    assert mine.action == "SKIP" and mine.fill is None
                if isinstance(app.screen, RoundScreen):  # computers still racing: watch, then skip ahead
                    assert app.screen.query_one("#buy", KeyButton).disabled
                    await pilot.press("enter")
                    await pilot.pause()
            assert isinstance(app.screen, ResultScreen)
            assert game.round.decisions[YOU].action == {"b": "BUY", "s": "SELL", "k": "SKIP", "timeout": "TIMEOUT"}[step]
            assert all(s in game.round.decisions for s in range(4))
            await pilot.press("enter")
            await pilot.pause()
        assert isinstance(app.screen, RecapScreen)
        board = {name: total for _, name, total in leaderboard(game)}
        assert board["YOU"] == game.total(YOU)
        await pilot.press("e")
        await pilot.pause()
        assert (isolated_home / "etf_session_7.csv").exists()

    record = json.loads((isolated_home / "etf_history.jsonl").read_text().splitlines()[-1])
    assert record["game"] == "etf" and record["seed"] == 7 and record["mode"] == "EASY"
    assert record["rounds_played"] == 6


def event_seed() -> int:
    return next(s for s in range(500) if draw_market(HARD.replace(seed=s), random.Random(s)).rounds[0].event)


async def test_hard_event_round_shows_the_banner_and_flags_the_row():
    seed = event_seed()
    app = build_app(parse_args(["etf", "--seed", str(seed)]))
    app.etf_clock = FakeClock()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("down", "down", "enter")  # HARD
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, RoundScreen) and screen.game.mode == "HARD"
        event = screen.game.round.plan.event
        assert event is not None
        banner = str(screen.query_one("#event-banner", Static).content)
        assert banner.startswith(f"⚑ {event.ticker}") and "weight" in banner
        tickers = list(screen.query_one("#basket", Static).content.columns[0].cells)
        assert f"⚑ {event.ticker}" in [str(c) for c in tickers]
        chg = [str(c) for c in screen.query_one("#basket", Static).content.columns[3].cells]
        assert event.chg_label in chg


async def test_home_lists_all_five_games_and_etf_lobby():
    app = MTTGamesApp()
    async with app.run_test(size=SIZE) as pilot:
        rows = [str(r) for r in app.screen.query_one("#game-list").rows]
        assert [r.split()[0] for r in rows] == ["CARD", "DICE", "TRADING", "OUTCRY", "ETF"]
        await pilot.press("down", "down", "down", "down", "enter")
        await pilot.pause()
        lobby = app.screen
        assert isinstance(lobby, LobbyScreen) and lobby.ui.source.key == "etf"
        assert "price the basket · trade the gap · beat the traders to it" in str(
            lobby.query_one("#subtitle", Static).content)
        assert "NAV = Σ weight × price" in str(lobby.query_one("#lobby-note", Static).content)
        labels = list(lobby.query_one("#modes-table", Static).content.columns[0].cells)
        assert "trader error sd · decision time" in labels and "size at bid / ask" in labels
        for key in ("h", "c"):
            await pilot.press(key)
            await pilot.pause()
            assert not isinstance(app.screen, LobbyScreen)
            await pilot.press("escape")
            await pilot.pause()


async def test_escape_quits_to_the_lobby():
    app = build_app(parse_args(["etf", "--seed", "3"]))
    app.etf_clock = FakeClock()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RoundScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, LobbyScreen)


# ── the W × P column ─────────────────────────────────────────────────────────


def wxp_cells(table):
    return table.columns[-1].cells


@pytest.mark.parametrize("cfg,places", [(EASY, 0), (MEDIUM, 1), (HARD, 2),
                                        (EASY.replace(stocks=3, weight_places=2, price_places=2), 2)],
                         ids=["EASY", "MEDIUM", "HARD", "CUSTOM"])
def test_wxp_column_at_the_difficulty_precision(cfg, places):
    for seed in range(5):
        g = EtfGame(cfg.replace(seed=seed))
        plan = g.round.plan
        table = basket_table(g, plan)
        cells = list(wxp_cells(table))
        for i in range(len(plan.tickers)):
            expected = (plan.shown_weights[i] * plan.prices[i]).quantize(plan.tick, rounding=ROUND_HALF_UP)
            assert str(cells[i]) == f"{expected:,.{places}f}"
            assert ("." in str(cells[i])) == (places > 0)  # whole numbers on EASY, no decimal point
        prices = [str(c) for c in table.columns[2].cells][:-1]
        assert all(("." in p) == (places > 0) and (places == 0 or len(p.split(".")[1]) == places) for p in prices)
        assert str(cells[-1]) == "Σ = ?"  # the sum is still yours to do
        assert table.columns[-1].justify == "right"


def test_round_screen_quote_and_buttons_use_the_difficulty_precision():
    for cfg, text in ((EASY, lambda x: f"{x:.0f}"), (MEDIUM, lambda x: f"{x:.1f}"), (HARD, lambda x: f"{x:.2f}")):
        g = EtfGame(cfg.replace(seed=4))
        plan = g.round.plan
        assert text(plan.bid) == str(plan.bid) and text(plan.ask) == str(plan.ask)


def test_event_row_wxp_uses_the_shown_weight_and_nav_does_not():
    seed = event_seed()
    g = EtfGame(HARD.replace(seed=seed))
    plan = g.round.plan
    k = plan.row(plan.event.ticker)
    stale = (plan.shown_weights[k] * plan.prices[k]).quantize(plan.tick, rounding=ROUND_HALF_UP)
    adjusted = (plan.weights[k] * plan.prices[k]).quantize(plan.tick, rounding=ROUND_HALF_UP)
    assert stale != adjusted
    cell = list(wxp_cells(basket_table(g, plan)))[k]
    assert str(cell) == f"{stale:,.2f}" and "#F2C14E" in str(cell.style)  # stale value, marked amber
    assert plan.nav == nav(plan.weights, plan.prices, plan.tick) != nav(plan.shown_weights, plan.prices, plan.tick)
    solved = list(wxp_cells(basket_table(g, plan, solved=True)))
    struck = solved[k]
    assert str(struck) == f"{stale:,.2f} {adjusted:,.2f}"
    struck_spans = [span for span in struck.spans if "strike" in str(span.style)]
    assert [(sp.start, sp.end) for sp in struck_spans] == [(0, len(f"{stale:,.2f}"))]  # only the stale value
    assert "strike" not in str(struck.style)
    assert str(solved[-1]) == f"Σ = {plan.nav:,.2f}"


def test_change_column_and_last_nav_title():
    g = EtfGame(MEDIUM.replace(seed=3))
    g.skip()
    g.advance_to(g.round.start + 4 * MEDIUM.timer_s)
    g.next_round()
    plan = g.round.plan
    table = basket_table(g, plan)
    assert [c.header for c in table.columns] == ["TICKER", "WEIGHT", "PRICE", "CHG", "%", "Δ W × P", "W × P"]
    deltas = [str(c) for c in table.columns[5].cells][:-1]
    total = sum(Decimal(d) for d in deltas)
    assert g.market.nav_before(2) + total == plan.nav  # what the player can add up
    assert all(len(d.lstrip("+-").split(".")[1]) == 1 for d in deltas if d != "0")  # tenths on MEDIUM
    from mtt_games.games.etf.screens.common import last_nav_title

    assert last_nav_title(g, plan, "BASKET") == f"BASKET · last NAV {g.rounds[0].plan.nav:.1f}"
