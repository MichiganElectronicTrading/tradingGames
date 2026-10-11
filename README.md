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

## Higher or Lower

```bash
met-games hilo                      # lobby: EASY · MEDIUM · HARD · RED/BLACK · CUSTOM…
met-games hilo --seed 7 --deck full # same deck order for everyone; --deck interview|full|redblack
```

**Rules.** One card is showing. Call the next card HIGHER or LOWER and stake a whole percent of your capital (0 = sit out). Bets pay even money. A same-rank card is a push. Aces are low (A=1 … K=13). Bets are untimed: take as long as you like. If capital falls below 1 you bust, which ends the game.

**Keys.**

| key | does |
|---|---|
| H / L or ↑ / ↓ (R / B or ↑ / ↓ on red/black) | pick the side: ↑ HIGHER (RED), ↓ LOWER (BLACK) |
| 0–9 | stake 0–90% |
| A | all-in |
| ← → | −5% / +5% |
| Shift+← / Shift+→, or [ / ] | previous / next multiple of 25% (0 · 25 · 50 · 75 · 100): 60 → 75 → 100, 60 → 50 → 25 |
| ⏎ | lock (or skip the reveal) |

With quick lock on (the default), pressing 0–9 or A after picking a side locks the bet immediately; the arrow keys and [ ] never lock. The bet screen's STAKE GUIDE panel shows these keys and your current combo.

**Timed bets (Custom).** Turn on "timed bets" in Custom to get the old clock back, with the time per bet set in seconds (2–30). Each bet then has its own clock; running out is a stake-0 MISS that resets the streak. Speed multipliers apply, and the bet screen shows the CLOCK panel in place of the STAKE GUIDE.

**Kelly sizing.** Among the cards left, h are higher than the showing card, l are lower, and the rest are the same rank. On an even-money bet the Kelly fraction is **k = |h − l| ÷ (h + l)** on the side with more cards; a push returns the stake, so it doesn't change k. If h = l there is no edge and the right play is to sit out. On red/black, k = |reds − blacks| ÷ (reds + blacks).

**Grading.** Let s be your stake as a fraction of capital.

| grade | when | points |
|---|---|---|
| PERFECT | right side, \|s − k\| ≤ max(0.10k, 3%) | 100 |
| GOOD | right side, \|s − k\| ≤ max(0.25k, 7%) | 60 |
| OK | right side, further off | 20 |
| DISCIPLINE | no edge and you sat out | 50 |
| SAT OUT | there was an edge and you sat out | 0 |
| MISS | wrong side, or staked with no edge (timed bets: also running out of time) | 0 |

**Scoring.** Points = base × combo, rounded half up.
- **Combo:** ×(1 + 0.1 × streak), capped at ×3. PERFECT, GOOD and DISCIPLINE extend the streak; OK keeps it; MISS and SAT OUT reset it.
- **Speed (timed bets only):** points = base × speed × combo. LIGHTNING ×2 if you lock in the first 25% of the bet's clock; FAST ×1.5 in the first 50%. Speed only applies to PERFECT, GOOD and DISCIPLINE, and a timeout also resets the streak.
- **End of game:** if you finish above your start without busting, you get a capital bonus of round(1000 × log2(final ÷ start)).
- **End screen:** shows your multiple next to the **Kelly benchmark** (staking exactly k on the right side every bet of the same deck order) and your **worst bet** (the most points lost against the best play).
- **High scores:** the top 10 for each deck and difficulty are kept in `~/.met_games/hilo_scores.json`. Untimed and timed games have separate tables; press T on the HIGH SCORES screen to switch.

**Decks.**

| deck | cards | bets |
|---|---|---|
| Interview | one of each rank, A–K | 12 |
| Full | 52 | 51 |
| Red/Black | 52, call the color | 52 |

**Difficulty.**

| | EASY | MEDIUM | HARD |
|---|---|---|---|
| default deck | Interview | Full | Full |
| time per bet | untimed | untimed | untimed |
| board shows | counts, lower/same/higher and odds | counts and lower/same/higher | cards left and the last three |

Press D in the lobby to switch decks.

### Decisions (Hi/Lo)

- **Lobby:** RED/BLACK is a shortcut for MEDIUM on the red/black deck. The deck picker keeps your choice once you press D (or pass `--deck`); otherwise each difficulty shows its default deck.
- **Interview deck:** the suit of each rank comes from the seed, so the same seed gives the same suits.
- **Red/black:** there is no showing card; you bet on all 52 cards.
- **Odds:** h, l and same are counted over every card left, including same-rank cards, which push.
- **Grading:** k = 0 is checked first, so any stake on a no-edge bet is a MISS.
- **Clock:** with timed bets, the clock is paused during the reveal flash (0.6s, or ⏎ to skip); the next bet's clock starts when it opens.
- **Untimed by default:**
  - The presets no longer carry a time per bet. Custom's "timed bets" toggle uses its seconds field, which starts at 10s for every preset; the old 6s (MEDIUM) and 4s (HARD) are gone.
  - Untimed bets are graded at NORMAL speed (×1), so the review and LAST BETS never show a speed tier.
  - The end screen's GRADES panel keeps best combo and best streak, but drops the LIGHTNING / FAST counts.
- **Stake keys:**
  - The key bar keeps "H/L side" in front of the new key list.
  - Shift+arrows and [ ] snap from the current stake: a stake already on a multiple moves a full 25%, so 25 → 50 and 25 → 0.
- **High-score tables:**
  - The tables are now keyed deck/mode/untimed or deck/mode/timed, and each entry records `timed`.
  - Every score saved before this change came from a timed game, so the old deck/mode tables are read as timed tables.
- **Benchmark:** stakes are floored to whole dollars, to match how your own stakes are sized (capital × percent, floored).
- **Capital bonus:** measured against the starting capital; there is no bonus if you bust or finish at or below the start.
- **Rounding:** points round half up.
- **Worst bet:** measured against the best available grade at that bet's speed and combo. That is PERFECT, or DISCIPLINE on a no-edge bet, so a correct sit-out is never the worst bet.
- **High scores:**
  - Kept per deck and difficulty; CUSTOM games have their own board.
  - Ties keep the earlier score ahead.
  - The lobby's STATS entry is replaced by HIGH SCORES. Every finished game is also appended to `~/.met_games/hilo_history.jsonl`.
- **Shared code:** the Custom screen gained a `custom_note` hook (Hi/Lo has no settle range), and the CLI gained `--deck`.
- **Existing tests:** the only changes are the list-of-games assertions, which now include HI/LO.

### Decisions (rename)

- **Old command:** `mtt-games` still works as an alias. It runs the same app after printing one dim notice. **Remove it in a future version**, along with the `MTT_GAMES_HOME` fallback; the `~/.mtt_games` migration can go once everyone has upgraded.
- **Migration:** `~/.mtt_games` is copied (never moved or deleted) into `~/.met_games`, only when the new folder doesn't exist yet and no data-folder env var is set. One dim line on the terminal says it happened.
- **Line widths:** "MTT" → "MET" keeps every string's length. The home-screen title and the project description get 4 characters shorter, so nothing re-wraps and no padding was needed.
- **Seeds:** a test pins seed 1234's first deal in all six games to the values from before the rename.
