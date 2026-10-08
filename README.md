# mtt-games

Solo trading drills for **MTT (Michigan Trading and Technology)**, in your terminal.

There are three games. Card and Dice are market-taking drills built on the same core:

- **Card Game**: cards are dealt from a deck and prices are whole dollars.
- **Dice Game**: dice are rolled and prices move in **0.25 ticks**.
- **Trading Game**: a market-making drill. You and three computer traders take turns making two-way markets on one deal of cards; see [Trading Game](#trading-game).

In Card and Dice, some items are face up. A market maker quotes a two-way price on the sum of all of them, and you buy, sell, or pass before the timer runs out. After the reveal you report your own P&L. The game then grades your decision on **edge** (was it a good trade at the time?) separately from **luck** (how the draw went).

## Install & run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv run mtt-games            # run from the repo (creates the venv on first run)
# or install it as a tool:
uv tool install .
mtt-games
```

`python -m mtt_games` also works inside the venv. Run the tests with `uv run pytest`.

The app opens on the **MTT GAMES** home screen, which lists the available games. Press ⏎ on a game to reach its lobby.

```bash
mtt-games card              # skip the home screen and open the Card Game lobby
mtt-games dice              # ... or the Dice Game lobby
mtt-games trade             # ... or the Trading Game lobby
mtt-games dice --seed 42    # every session this run uses seed 42
mtt-games --help
```

## Club play

To run a head-to-head drill, pick a seed and have everyone run the same command:

```bash
mtt-games card --seed 1234      # or: mtt-games dice --seed 1234 / mtt-games trade --seed 1234
```

Everyone then plays the same game and mode. With the same seed, everyone gets identical deals, events, flips and quotes, so the only differences are the decisions people make. When the session ends, compare recaps; each one shows `SEED 1234` in its top bar. FINAL BALANCE shows who made the most money, but EDGE TAKEN is the fairer score, since LUCK is the same draw for everyone. Pressing R on the recap replays the seed for a rematch.

## Controls

| Screen | Keys |
|---|---|
| Home | ↑↓ move · ⏎ open · Q quit |
| Lobby | ↑↓ move · ⏎ start · C custom · H how to play · Q quit · Esc home |
| Custom | ↑↓ move · ←→ change value · Tab next panel · Space toggle event · ⏎ start (settings) / toggle (events) / load (presets) · S save preset · Esc back |
| Round | B buy at the ask · S sell at the bid · P pass · ←→ size ±1 · shift+←→ size ±5 (choose-size modes) |
| Reveal | type your P&L (digits and `-`; Dice also takes `.`) + ⏎ · W explain fair value · ⏎ next round |
| Recap | R replay same seed · N next difficulty · E export CSV · L lobby · Q quit |
| Trading Game · your market | type BID / ASK / SIZE (digits and `-`) · Tab next field · ⏎ show market |
| Trading Game · fills | ⏎ skip the feed · ⏎ continue |
| Trading Game · their market | B buy at the ask · S sell at the bid · P pass · ←→ size ±1 · ⏎ next turn (after you act) |
| Trading Game · settle | type your hand P&L + ⏎ · W walkthrough · ⏎ next hand |
| How to play | ↑↓ scroll · Esc back |
| Stats | C clear stats (asks Y/N first; clears only this game's history) · Esc back |

## The games

Card Game: Trading against a market on hidden card values

Dice: Game: Trading against a market on hidden dice values with smaller tick sizing

Trading Game: Making a market and taking against bot markets on hidden card values


Outcry: Open market outcry across different rounds, trading a contracts hidden true value.