"""Seeds stay compatible: `--seed 1234` deals the same first hand in every game, pinned to the values it
dealt before the package rename. If one of these changes, shared seeds and saved history stop matching."""

from decimal import Decimal as D

from met_games.games.card.config import MEDIUM as CARD
from met_games.games.card.engine import CardSession
from met_games.games.dice.config import MEDIUM as DICE
from met_games.games.dice.engine import DiceSession
from met_games.games.etf.config import MEDIUM as ETF
from met_games.games.etf.engine import EtfGame
from met_games.games.hilo.config import MEDIUM as HILO
from met_games.games.hilo.engine import HiloGame
from met_games.games.outcry.config import MEDIUM as OUTCRY
from met_games.games.outcry.engine import OutcryGame
from met_games.games.trade.config import MEDIUM as TRADE
from met_games.games.trade.engine import TradeSession

SEED = 1234
CARDS = [(12, "♦"), (13, "♥"), (14, "♥"), (9, "♣"), (7, "♦")]


def test_card_first_deal():
    r = CardSession(CARD.replace(seed=SEED), "MEDIUM").new_round()
    assert [(c.rank, c.suit) for c in r.items] == CARDS
    assert r.tape[0] == (0.0, 40, 43)


def test_dice_first_deal():
    r = DiceSession(DICE.replace(seed=SEED), "MEDIUM").new_round()
    assert [d.face for d in r.items] == [1, 1, 5, 1, 6]
    assert r.tape[0] == (0.0, D("16.50"), D("18.00"))


def test_trade_first_deal():
    h = TradeSession(TRADE.replace(seed=SEED), "MEDIUM").new_hand()
    assert [(c.rank, c.suit) for c in h.items] == CARDS
    assert h.peeks == {"DELTA": 1, "GAMMA": 0, "THETA": 3}
    t = h.turns[0]
    assert (t.maker, t.bid, t.ask, t.size) == ("DELTA", 41, 43, 5)


def test_outcry_first_deal():
    s = OutcryGame(OUTCRY.replace(seed=SEED), "MEDIUM").setup
    assert (s.low, s.high) == (57, 86)
    assert s.numbers == (60, 57, 59, 86, 82, 75, 58, 78)
    assert s.styles == (None, "MAKER", "SNIPER", "PASSIVE", "SNIPER", "ANCHOR", "MAKER", "CHASER")
    assert s.openers == (0, 0, 5, 7, 7, 2, 1)
    assert s.trader_seeds[1] == 836177933542809307


def test_etf_first_deal():
    p = EtfGame(ETF.replace(seed=SEED), "MEDIUM").round.plan
    assert p.tickers == ("HD", "MSFT", "AAPL", "KO", "XOM")
    assert p.prices == (D("242.3"), D("64.2"), D("75.2"), D("62.1"), D("333.4"))
    assert p.weights == (D("0.09"), D("0.10"), D("0.06"), D("0.37"), D("0.38"))
    assert (p.bid, p.ask) == (D("180.4"), D("180.6"))


def test_hilo_first_deal():
    g = HiloGame(HILO.replace(seed=SEED), "MEDIUM")
    assert [str(c) for c in g.cards[:8]] == ["8♦", "Q♣", "6♥", "9♦", "6♣", "8♥", "K♠", "6♦"]
