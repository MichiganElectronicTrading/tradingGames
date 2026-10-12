# MET Trading Games — Michigan Electronic Trading

Solo trading drills for **MET (Michigan Electronic Trading)**, in your terminal.

There are three games. Card and Dice are market-taking drills built on the same core:

- **Card Game**: cards are dealt from a deck and prices are whole dollars.
- **Dice Game**: dice are rolled and prices move in **0.25 ticks**.
- **Trading Game**: a market-making drill. You and three computer traders take turns making two-way markets on one deal of cards; see [Trading Game](#trading-game).

In Card and Dice, some items are face up. A market maker quotes a two-way price on the sum of all of them, and you buy, sell, or pass before the timer runs out. After the reveal you report your own P&L. The game then grades your decision on **edge** (was it a good trade at the time?) separately from **luck** (how the draw went).

## Install & run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv run met-games            # run from the repo (creates the venv on first run)
# or install it as a tool:
uv tool install .
met-games
```

`python -m met_games` also works inside the venv. Run the tests with `uv run pytest`.

The app opens on the **MET GAMES** home screen, which lists the available games. Press ⏎ on a game to reach its lobby.

```bash
met-games card              # skip the home screen and open the Card Game lobby
met-games dice              # ... or the Dice Game lobby
met-games trade             # ... or the Trading Game lobby
met-games dice --seed 42    # every session this run uses seed 42
met-games --help
```

## Upgrading from mtt-games

This project used to be **mtt-games**, for MTT (Michigan Trading and Technology). It is now **met-games**, for MET (Michigan Electronic Trading). Seeds are unchanged, so `--seed N` deals the same game as before. On first run, your history is copied from `~/.mtt_games` to `~/.met_games`; the old folder is left in place. `MTT_GAMES_HOME` still works if `MET_GAMES_HOME` is unset. To swap the installed command:

```bash
uv tool uninstall mtt-games
uv tool install --force --editable .
```

## Club play

To run a head-to-head drill, pick a seed and have everyone run the same command:

```bash
met-games card --seed 1234      # or: met-games dice --seed 1234 / met-games trade --seed 1234
```

Everyone then plays the same game and mode. With the same seed, everyone gets identical deals, events, flips and quotes, so the only differences are the decisions people make. When the session ends, compare recaps; each one shows `SEED 1234` in its top bar. FINAL BALANCE shows who made the most money, but EDGE TAKEN is the fairer score, since LUCK is the same draw for everyone. Pressing R on the recap replays the seed for a rematch.


## The games

Card Game: Trading against a market on hidden card values

Dice: Game: Trading against a market on hidden dice values with smaller tick sizing

Trading Game: Making a market and taking against bot markets on hidden card values

Outcry: Open market outcry across different rounds, trading a contracts hidden true value.

ETF Arb: Price a basket of stocks and race 3 traders to trade the ETF when it drifts from its NAV

Hi/Lo: Call the next card higher or lower (or red or black) and size each even-money bet by the Kelly criterion, against the clock

Math: Mental math drills with exact answers: arcade sprints, Zetamac and Optiver-style test drills, a weakness report, and a daily challenge
