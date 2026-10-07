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

Card and Dice share the same rules, flow, screens and scoring. They differ only in what gets dealt and the tick size.

- **Card Game:** a standard 52-card deck, with 2–10 at face value, J=11, Q=12, K=13 and A=14. There's a fresh shuffle every round.
- **Dice Game:** fair six-sided dice, each an independent roll from 1 to 6. Prices sit on a 0.25 tick, and money is shown to the cent.

Rules for both:
- The round **settles** at the sum of everything dealt, after any market event.
- The market maker shows `BID @ ASK`. You can buy at the ask, sell at the bid, or pass, with at most one trade per round.
  - Long P&L = `(settle − ask) × size`, short P&L = `(bid − settle) × size`.
- **Budget rule:** a position is only allowed if its worst-case loss fits in your balance.
  `max_long = ⌊balance / (ask − settle_min)⌋` and `max_short = ⌊balance / (settle_max − bid)⌋`.
  A side that can't lose (denominator ≤ 0) is capped at 100, and both sides are capped at 100. A side whose max is below 1 is disabled.
- When the timer hits 0 you auto-pass, and the round is logged as *timed out*.
- After the reveal you must type your round P&L. Reporting never changes your balance; it's tracked as a stat.
- The session ends early if your balance reaches 0, or if a new round opens with **neither side tradable** (max long < 1 and max short < 1). The second case is reported as *out of risk capacity*. The recap shows the reason in a banner.

### Market events

On each round, with probability `event_freq` (0, 1/3 or 1), one enabled event is announced before the quote.

Card events:

| key | effect |
|---|---|
| `face_ten` | J, Q, K count as 10 |
| `no_twos` | all 2s are removed from the deck before the deal |
| `aces_one` | aces count as 1 |
| `double_hidden` | one hidden card counts double (you never learn which until the reveal) |
| `red_negative` | hearts and diamonds count negative, face-up ones included |

Dice events replace the six face values [1, 2, 3, 4, 5, 6], which stay equally likely. The new values apply to face-up and hidden dice alike. Under `high_only` a die is drawn as its value (5 or 6 pips). Under the other events it shows the rolled face with the adjusted value struck through next to it.

| key | faces | banner |
|---|---|---|
| `high_only` | 5, 5, 5, 6, 6, 6 | only 5s and 6s this round |
| `one_is_seven` | 7, 2, 3, 4, 5, 6 | a 1 is worth 7 this round |
| `six_is_zero` | 1, 2, 3, 4, 5, 0 | 6s count as 0 this round |
| `evens_double` | 1, 4, 3, 8, 5, 12 | even dice count double |
| `odds_negative` | −1, 2, −3, 4, −5, 6 | odd dice count negative |
| `double_hidden` | standard | one hidden die counts double |

### Hard mode extras

In Hard mode, at a random moment between 30% and 60% of the timer, one hidden card or die **flips face up** (tagged NEW). Fair value and the range move. With probability 0.5 the market maker **doesn't requote** (a stale quote). The tape shows the last two quotes, and the game never tells you whether the quote is stale.

### Presets

Card Game:

|                | EASY     | MEDIUM | HARD                     |
|----------------|----------|--------|--------------------------|
| cards          | 3        | 5      | 6–8 (random per round)   |
| face up        | 0–1      | 0–2    | 1–3                      |
| rounds         | 4        | 4      | 6                        |
| timer          | 60s      | 30s    | 15s                      |
| spread         | 4        | 3      | 2                        |
| quote_noise_sd | 3.0      | 2.0    | 1.5                      |
| sizing         | fixed 1  | choose | choose                   |
| mid-round flip | off      | off    | on                       |
| stale quotes   | off      | off    | on                       |
| events         | off      | off    | every round, all enabled |
| budget         | $500     | $500   | $500                     |

Dice Game:

|                               | EASY    | MEDIUM | HARD                     |
|-------------------------------|---------|--------|--------------------------|
| dice                          | 3       | 5      | 6–8                      |
| face up                       | 0–1     | 0–2    | 1–3                      |
| rounds                        | 4       | 4      | 6                        |
| timer                         | 60s     | 30s    | 15s                      |
| spread                        | 2.00    | 1.50   | 1.00                     |
| quote_noise_sd                | 1.50    | 1.00   | 0.75                     |
| sizing                        | fixed 1 | choose | choose                   |
| mid-round flip / stale quotes | off     | off    | on                       |
| events                        | off     | off    | every round, all enabled |
| budget                        | $500    | $500   | $500                     |

**Custom** starts from EASY and lets you edit every config field. Price fields step in the game's tick. Press S to save the result as a named preset; saved presets go to `~/.mtt_games/<game>_presets.json` and appear under PRESETS.

## Trading Game

You plus three computer traders (DELTA, GAMMA, THETA) sit at a table. Each **hand** is one deal of cards (Card's rules, values, events and fair-value math) and has **four turns**. On each turn one player makes a two-way market and the other three may trade it. The cards stay the same for all four turns, and positions and cash carry from turn to turn. After turn 4 the cards flip and every position settles at the sum. The four hand P&Ls always add up to $0 (the engine checks this every hand).

### A hand

1. **Deal** with Card's rules: n cards, a face-up count in range, and an optional event.
2. **Seat order** is a random permutation of YOU, DELTA, GAMMA, THETA. The player in seat i makes on turn i, so everyone makes exactly once.
3. **Peeks** (private information). On Medium and Hard each trader peeks at one hidden card: distinct random cards when there are 3 or more hidden, otherwise card `j mod k` for trader j (DELTA=0, GAMMA=1, THETA=2). On Easy, one random trader peeks and the other two see nothing. With no hidden cards, nobody peeks.
4. **Four turns.** On Hard, between turns 1→2, 2→3 and 3→4 one random hidden card turns face up (never the last hidden one), and the public fair and range update. The next turn's table shows `▲ X turned face up`.
5. **Settle:** reveal everything; settle = sum. Each player's hand P&L = `cash + position × settle`.
6. **Report:** you type your own hand P&L, an integer that must match exactly. Then balances and standings update.

### A turn

- **Your market.** Type `bid`, `ask` and a size per side. Width (`ask − bid`) must be inside the mode's allowed range, and the size is fixed at 5 on Easy and 1–10 otherwise. The traders then act on it in seat order, and the fills feed shows one line about every 0.6 s (⏎ skips). If the quote timer runs out you post nothing and the turn passes with no trades.
- **A trader's market.** You act first: buy at the ask, sell at the bid (up to what's left on that side), or pass. Take-timer expiry counts as a pass. The other traders act after you, in seat order, and each side's size depletes as it fills.

### How the computer traders think

The traders make no random choices; their behavior depends only on the game state.

- **private_fair** is the exact conditional fair given the face-up cards plus the trader's peeked card, while that card is still hidden. It's Card's fair-value math with the peeked card treated as known. Once the card flips, private fair is just public fair.
- **est** = `private_fair + learned_offset`, clamped to the trader's settle range. The offset starts at 0 every hand.
- **As maker:** `mid = public_fair + 0.5 × (est − public_fair)`, `bid = round(mid − w/2)`, `ask = bid + w`, size 5 per side, where `w` is the mode's trader width. The trader shades half-way toward what it knows.
- **As taker:** buy `min(5, remaining)` at the ask if `est ≥ ask + 1`, sell at the bid if `est ≤ bid − 1`, otherwise pass. A trader that buys your ask is telling you it thinks the sum is at least ask + 1.
- **Learning (Hard only, learn_rate 0.25):** after every fill each trader updates `learned_offset += learn_rate × (target − est)`, where `target = price + 1` if the aggressor (the taker, never the maker) bought and `price − 1` if it sold. All fills are public. Easy and Medium traders never learn from the table. That is deliberately exploitable, and exploiting it is the lesson.

### Your risk

Your hand P&L is linear in the settle, so the worst case is at `settle_min` or `settle_max`. Every action must keep the worst-case loss of your whole hand position (everything you've done this hand) within your balance:

- **Quotes** are checked as if all of the bid fills, all of the ask fills, and both fill. An invalid quote is rejected with a message saying which case breaches.
- **Takes** are capped to the largest size that fits, and a side that can't take 1 unit is disabled.

The traders have no budget limit.

### Scoring

- **Making P&L** is the P&L of fills on your own market; **taking P&L** is the P&L of your trades on the others'. Both settle at the final sum, and together they equal your hand P&L.
- **Table fair** is the fair given the face-up cards plus every card any trader peeked at. It's the yardstick for the edge of your takes (`table_fair − ask` for a buy, `bid − table_fair` for a sell) in the recap and in mistakes.
- **Mistakes** listed on the recap: hands where your making P&L was negative (with how many units traders who peeked took off you), takes with negative edge vs table fair, wrong P&L reports, and timeouts.

### Trading Game presets

|                    | EASY      | MEDIUM | HARD                    |
|--------------------|-----------|--------|-------------------------|
| cards              | 3         | 5      | 6–8                     |
| face up            | 0–1       | 0–2    | 1–3                     |
| hands              | 4         | 4      | 6                       |
| your quote timer   | 45s       | 30s    | 15s                     |
| your take timer    | 30s       | 20s    | 10s                     |
| your allowed width | 2–6       | 1–4    | 1–3                     |
| your quote size    | 5 fixed   | 1–10   | 1–10                    |
| trader width       | 4         | 2      | 2                       |
| peeks              | 1 trader  | all 3  | all 3                   |
| flip between turns | no        | no     | yes                     |
| learn_rate         | 0         | 0      | 0.25                    |
| events             | off       | off    | every hand, all enabled |
| budget             | $500      | $500   | $500                    |

Every field is editable in Custom.

### Trading Game screens

- **Your market:** TABLE (cards, `face up S · hidden k · settles MIN–MAX`), YOUR MARKET with large BID / ASK / SIZE inputs, a width check, a worst-case line and SHOW MARKET. The right column has TIMER, the TABLE of traders with your seat this hand, and STANDINGS.
- **Fills:** your market, the feed (`TIME · WHO · ACTION · FILL · YOUR POSITION`) and a footer with bid/ask filled, `round trips × width = locked $`, and the open position. The right column has WHAT YOU LEARNED (one line per trader) and NEXT.
- **A trader's market:** the TABLE plus MARKETS SO FAR on the left. On the right: that trader's market, YOUR ORDER, TIMER and YOUR POSITION.
- **Settle:** all cards up with `= SUM`, who peeked at what, the HAND LEADERBOARD (your P&L is `??` until you report), REPORT YOUR HAND P&L and YOUR TRADES. Press W for a walkthrough with the hand's real numbers.
- **Recap:** FINAL STANDINGS; MAKING / TAKING / BALANCE / REPORTS tiles; the HANDS table (losing hands on dark red, with a TOTAL row); MISTAKES; BANKROLL.

Every screen has a top bar (`TRADING GAME ▸ MODE · HAND h / n · BAL $x`) and a turn bar (`① YOU MAKE ▸ ② DELTA ▸ … ▸ SETTLE` in this hand's seat order).

## How fair value is computed

### Card Game

Let `up` be the (event-adjusted) values of the face-up cards, and `rest` the values of **every card you can't see**. That's the deck minus the face-up cards, minus anything an event removed; it includes both the hidden dealt cards and the undealt ones. Let `k` be the number of hidden cards.

Each hidden card is a uniform draw (without replacement) from `rest`. By linearity of expectation, each one is worth `mean(rest)` on average:

```
fair       = sum(up) + k × mean(rest)
settle_min = sum(up) + sum of the k smallest values in rest
settle_max = sum(up) + sum of the k largest values in rest
```

With `double_hidden`, one hidden card is counted twice, so there are effectively `k + 1` draws: `fair = sum(up) + (k+1) × mean(rest)`. The minimum adds the single smallest value again and the maximum adds the single largest again.

Example: two cards face up, K♠ and 5♥ (`sum(up) = 18`), with 3 hidden. `rest` is the other 50 cards, whose values add up to `416 − 18 = 398`, so `mean(rest) = 7.96` and `fair = 18 + 3 × 7.96 = 41.88`.

### Dice Game

Each die is an independent roll, so the face-up dice tell you nothing about the hidden ones. Let the active event's six face values have mean `m`, minimum `lo` and maximum `hi`. These are `[1..6]` with `m = 3.5` when there's no event.

```
fair       = sum(up) + k × m
settle_min = sum(up) + k × lo
settle_max = sum(up) + k × hi
```

With `double_hidden`, replace `k` with `k + 1`. Example: a 6 and a 2 face up with 3 dice hidden, no event: `fair = 8 + 3 × 3.5 = 18.5`, with a range of 11 to 26.

### Quotes, ticks and money (both games)

The quote is `mid = fair + N(0, quote_noise_sd)`, `bid = round_to_tick(mid − spread/2)`, `ask = bid + spread`. The tick is 1 for Card and 0.25 for Dice, and spreads are whole numbers of ticks.

Money math is exact. Card prices are ints, and Dice prices are `Decimal` multiples of 0.25, so P&L, balances and risk limits never pick up float drift. A Dice P&L report is correct if it equals the real P&L after both are rounded to cents, so 17.5, 17.50 and 17.499 all match 17.50. Fair value and edge are expectations and stay floats. **Edge** per unit at the moment you trade is `fair − ask` for a buy and `bid − fair` for a sell. Fair value is never shown before the reveal. On the reveal screen, W walks through the formula with the round's real numbers.

The tests check all of this against brute force:

- **Card, small `k`:** exhaustive enumeration of every hidden combination and every choice of doubled card. This is the proof of exactness.
- **Card, larger `k`:** 200k Monte Carlo draws, with a tolerance of 5 standard errors (`5 × sample_std / √200000`) computed for each case.
- **Dice:** exhaustive enumeration of all `6^k` outcomes for `k ≤ 4`, with an exact match.

The cases cover no event, each event, 0 face-up, and all-but-one face-up.

## Reproducibility

Each session uses a single `random.Random(seed)`. Every random draw a round could need is made when the round starts, in a fixed order: item count, face-up count, event, the deal (or roll), flip time/item/stale coin/requote noise, the doubled item, and quote noise. A session therefore replays exactly from its seed no matter when you press keys. The seed appears in the recap's top bar, the CSV filename and the history. R on the recap replays the same seed, and `--seed INT` fixes the seed for every session in a run.

## Files

Each game has its own files (`<game>` is `card`, `dice` or `trade`):

- `~/.mtt_games/<game>_history.jsonl`: one JSON line per finished session; that game's Stats screen reads this, and its CLEAR STATS button deletes it.
- `~/.mtt_games/<game>_presets.json`: your saved Custom presets.
- `./<game>_session_<seed>.csv`: a per-round export (for the Trading Game, one row per action on every market), written when you press E on the recap.

Set `MTT_GAMES_HOME=/some/dir` to use a different directory (the tests do this).

## Project layout

```
mtt_games/
  __main__.py          entry point (mtt-games [card|dice|trade] [--seed INT])
  app.py               App, game registry (GAMES), home screen
  theme.tcss           shared styles
  widgets.py           TitledPanel, TopBar, KeyBar, CardWidget, RowList, KeyButton, big digits
  storage.py           ~/.mtt_games read/write
  games/
    sumgame/           shared core for "trade the sum of partly hidden items" games
      config.py        SumConfig: every field but the item count; tick, price display, validation
      source.py        Source interface + Market (what a game plugs in)
      engine.py        round state machine, quotes on a tick, risk limits, exact P&L, edge, verdicts
      stats.py         recap math, history records, CSV rows
      ui.py            GameUI (banner, item widget, rules text) + config → UI registry
      screens/         lobby, custom, round, reveal, recap, howto, stats (+ common helpers)
    card/
      config.py        CardConfig + EASY/MEDIUM/HARD
      deck.py, events.py
      engine.py        CardSource (deck draws, fair value, range), Round, CardSession
      ui.py            CARD_UI (banner, CardWidget, rules)
    dice/
      config.py        DiceConfig (tick 0.25) + EASY/MEDIUM/HARD
      events.py        face-value events
      engine.py        DiceSource (independent rolls, fair value, range), DiceRound, DiceSession
      ui.py            DICE_UI + DieWidget
    trade/
      config.py        TradeConfig (a CardConfig) + EASY/MEDIUM/HARD
      engine.py        TradeSource, Hand/Turn/Action, TradeSession: seats, peeks, flips, traders, risk, settle
      stats.py         recap metrics, mistakes, history record, CSV rows
      ui.py            TRADE_UI: banner, Custom rows, how-to text, first-screen hook
      screens/         make, fills, take (turns.py), settle, recap (+ common helpers)
tests/                 math vs brute force, engine, config, dice, trade, Textual Pilot tests
```

Everything outside `screens/`, `ui.py` and `widgets.py` is plain Python with no Textual imports. The screens call into the engine, and the engine knows nothing about the UI.

## Adding a new game

If the new game is "trade the sum of some items, some face up", build it on `sumgame` the same way Card and Dice are built:

1. **Config.** Subclass `SumConfig` as a frozen dataclass. Set `NOUN`, `COUNT_FIELDS`, `TICK`, `PRICE_PLACES`, `SPREAD_MAX` and `EVENT_KEYS`, add the two item-count fields, and define `EASY`/`MEDIUM`/`HARD` presets.
2. **Source.** Subclass `Source` and implement `deal`, `value`, `market` (fair value and range), `settle_range`, `explain_notes` and `event_note`. Set `key`, `title`, `item`, `mean_label`, `config_cls`, `presets` and `events`. All randomness must go through the `rng` that `deal` receives.
3. **Round and session.** Add `class MyRound(Round): SOURCE = MY_SOURCE` and `class MySession(SumSession): ROUND = MyRound`.
4. **UI.** Write a widget that draws one item. It needs `show(face_up=, fresh=, tag=)`, a `tag` attribute and the `fresh` CSS class (see `DieWidget`). The widget factory is called as `make_widget(item, value, face_up, event)`; `event` is for display choices only. Then call `register(GameUI(...))` with the banner, tagline, widget factory and rules text.
5. **Register.** Add one line to `GAMES` in `mtt_games/app.py`:

   ```python
   GameInfo("yourgame", "YOUR GAME", "one-line tagline", partial(SumLobby, YOUR_UI)),
   ```

The home screen lists everything in `GAMES`, and the CLI accepts its key (`mtt-games yourgame`). A game that doesn't fit the sum model can still bring its own screens and register any lobby `Screen` factory in `GAMES`.

A game with its own round flow can still reuse the shared lobby, custom, how-to and stats screens, as the Trading Game does. `GameUI` has three optional hooks for this: `custom_fields` (the Custom rows), `howto` (the how-to sections) and `first_screen` (what `start_session` opens). The config can override `summary()` for the lobby's MODES table, and the shared Stats screen reads any history record with `mode`, `final_balance`, `edge_taken` and `reports_*`.

## Decisions

These are places where the spec left a choice open; in each case I picked the simplest option.

1. **Startup screen.** `mtt-games` opens on the home screen (the game list the layout asks for), and ⏎ opens the Card Game lobby. `mtt-games card` goes straight to the lobby. In both cases the home screen sits underneath, so Esc in the lobby returns home. The positional argument accepts any registry key, so a new game gets it automatically.
2. **Which cards are face up.** The first `n_up` cards of the shuffled deal are face up; since the deal is random, so is the choice.
3. **Pre-drawn randomness.** All of a round's random draws happen at round start, in a fixed order, even when they end up unused (for example, the flip draws when you trade before the flip). This is what makes replays independent of timing. A "random" seed is drawn once from `SystemRandom`, outside the session RNG, and then recorded.
4. **`double_hidden` edge cases.** The event is never chosen for a round with 0 hidden cards. The doubled card is never the one that flips. Under `double_hidden`, a flip is skipped if it would reveal the last hidden card.
5. **Flip with nothing hidden.** If a round has no hidden cards, there's no mid-round flip.
6. **Quote tape.** The tape only records quote *changes*. A stale quote adds no entry, so the tape simply doesn't move.
7. **Key pressed at the instant of a flip.** If the flip lands on the same tick as your B/S/P, the keypress is dropped and the new cards and quote are shown, so you never trade blind on stale information.
8. **Rounding.** The bid uses Python's `round()` (round-half-to-even).
9. **Pass verdicts.** "Missed edge" uses the best per-unit edge among the sides you were *allowed* to trade, at the quote and fair value in force when you passed. At ≥ 1.0/unit it's "missed edge of X/unit"; otherwise it's "correct pass". Timeouts are always "timed out".
10. **Ties in verdicts.** Edge of exactly 0 counts as a good trade, and P&L of exactly 0 counts as a good draw (or "lucky" for a bad trade).
11. **Sizing.** In choose mode there's a single size selector, clamped to `[1, max(max_long, max_short)]`. Each button shows the size it will actually trade, which is the chosen size clamped to that side's max.
12. **P&L reports.** A report is required every round, including passes and timeouts (the answer is 0).
13. **Validation additions.** Besides the required checks, the config also rejects: `stale_quotes` without `mid_round_flip`, events switched on with none enabled, `event_freq` outside {0, 1/3, 1}, a negative noise sd, a non-positive budget, and a non-integer seed.
14. **Custom editing.** ←→ only. Values clamp to each field's range: timer in steps of 5, budget $100–$10,000 in steps of $100, noise 0–6 in steps of 0.5. Seed goes "random" → 1, 2, …. Only valid configs can be saved, and the names EASY/MEDIUM/HARD are reserved.
15. **Custom's live settle range.** This is the lowest and highest settlement any round could produce: every card count in range, every possible event, all cards hidden.
16. **N (next difficulty).** It goes EASY → MEDIUM → HARD; HARD stays HARD, and CUSTOM goes to EASY. N uses a fresh random seed, while R reuses the current one. When `--seed` is given, N uses that seed too.
17. **Stats grouping.** Custom sessions are grouped under `CUSTOM` in Stats.
18. **Ending early.** Because the budget rule caps any loss at the current balance, the balance can only reach exactly $0, which ends the session ("balance hit $0").
    The more common way out is a low balance that can't cover a 1-unit worst case at the opening quote on either side. The engine checks this when it deals a round. If max long < 1 and max short < 1, that round is not played or recorded and the session ends "out of risk capacity". The check happens only at the start of a round; a mid-round flip doesn't trigger it. The round's random draws are still consumed, so replays stay identical.
19. **Lobby balance.** With no session running, the lobby's `BAL` shows the selected preset's starting budget.
20. **Timer display.** The timer shows remaining seconds rounded up, so the display never reads 00:00 while you can still act.
21. **`--seed`.** `--seed INT` (or `MTTGamesApp(seed=…)`) applies to every session in the run that doesn't set its own seed: presets, R, N, and Custom with seed "random". A Custom config with an explicit seed keeps that seed. The recap's top bar shows the seed in use.
22. **Monte Carlo tolerance.** The tolerance is 5 standard errors, computed for each case from the sample std. A flat 0.05 was too tight under `red_negative`, whose standard error is about 0.037. The test was checked for seeds 0–49 across all six event cases (300 runs, 0 failures), and the committed test keeps one fixed seed (7). Exactness is established by the enumeration tests.
23. **Extra widgets.** `widgets.py` also has `RowList` (selectable menu rows) and `KeyButton` (flat one-line buttons), so every screen shares the same classic look. The shared screens use a small helper module, `sumgame/screens/common.py`.
24. **Shared core naming.** The shared core is `games/sumgame/`. Card and Dice each subclass `SumConfig`, `Round` and `SumSession` and supply a `Source`. Card keeps its public names (`CardConfig`, `CardSession`, `Round`, `market_state`, …) so existing code and tests still import from `games/card/`. The Card-specific screens and `stats.py` were removed in favour of the shared ones, which changed import paths in `tests/test_app.py` only.
25. **Finding a game's UI.** Screens look up the `GameUI` from the config's class (`register` / `ui_for`). This let `start_session(app, config, mode, switch=…)` keep its signature.
26. **Config field names.** Each game names its own item-count fields (`n_cards_min`, `n_dice_min`), and the core reads them through `n_min`/`n_max`. Dice `spread` is a `Decimal`, and the budget stays whole dollars for both games.
27. **Dice spread range.** Card spreads are 1–8. Dice spreads are any whole number of ticks from 0.25 to 8.00, the same price range.
28. **Custom steps for Dice.** Spread steps by one tick (0.25). Quote noise steps by `min(0.5, tick)`, so Card keeps its 0.5 steps and Dice gets 0.25. Timer, budget and rounds are not prices and keep their steps.
29. **Report parsing.** Reports are parsed as `Decimal` from the typed text and compared after `ROUND_HALF_UP` rounding to cents, so 17.495 counts as 17.50. Card's input still accepts integers only, and an integer is trivially exact to the cent.
30. **Money types.** Money is `int` for Card and `Decimal` for Dice. History JSON stores Dice balances as floats; they're display values only, and play never reads them back.
31. **Dice event display.** Each dice event has a display mode, and the mode affects only how a die is drawn; the engine math is the same in both.
    - **remap** (`one_is_seven`, `six_is_zero`, `evens_double`, `odds_negative`, `double_hidden`): the die shows the face it rolled, with the value next to it struck through, the same way Card shows adjusted values. A rolled 1 under `one_is_seven` shows as one pip and `1=7`.
    - **value** (`high_only`): the die is drawn as its value, with 5 or 6 pips and a plain `=5`/`=6`. A die never shows 1–4 pips under this event.
    The mode lives on the event (`DiceEvent.display`). The item-widget factory receives the active event so it can choose the mode.
32. **Dice display.** Each die is a 9×5 frame plus a value line underneath, so dice rows are one line taller than card rows. The round log names a flipped die by its face ("▲ a 4 turned face up …").
33. **Dice names and tagline.** The dice events got short display names (HIGH ONLY, ONE IS SEVEN, SIX IS ZERO, EVENS DOUBLE, ODDS NEGATIVE, DOUBLE DOWN), and their banners use the spec's text. On the home screen the games are labelled "Card Expected Value", "Smaller Tick Sizing" and "You vs. 3-4 Traders".

34. **No mockups.** The spec says to match mockups, but no mockup files came with it (none in the repo or next to it). The Trading Game screens follow the spec's written descriptions of each panel, in the existing classic-TUI style.
35. **TradeConfig is a CardConfig.** It inherits Card's deal, face-up and event fields and their validation, and adds `quote_timer_s`, `width_min`/`width_max`, `peeks` and `learn_rate`. Five inherited fields are reused with a trading meaning, each with a named property: `rounds` = hands, `timer_s` = your take timer, `spread` = trader width, `sizing` = your quote size (`fixed` = 5, `choose` = 1–10), `mid_round_flip` = flip between turns. Validation messages are renamed to match. `quote_noise_sd` and `stale_quotes` are unused because the traders quote deterministically, and they're hidden from the lobby and Custom.
36. **Core hooks.** Four behavior-preserving additions:
    - `deal_items()`: the deal draws, moved out of `SumSession.new_round` in the same order.
    - `SumConfig`'s `describe()` now uses a config's `summary()` when it has one.
    - Optional `GameUI.custom_fields` / `howto` / `first_screen`.
    - `span()`: `_span` made public.

    Card and Dice behave exactly as before, and no existing test changed.
37. **DOUBLE DOWN with peeks.** The doubled card is drawn first, and the traders only peek at the other hidden cards. The doubled card also never flips (as in Card), so it is always among the cards nobody has seen. This makes "the existing fair-value math with the peeked card treated as known" exact, and it's tested against Card's enumeration helper. The peek rule (distinct when ≥ 3, else `j mod k`) is applied to that peekable list; without DOUBLE DOWN it is the hidden list itself.
38. **Peek details.** "Trader j" is DELTA=0, GAMMA=1, THETA=2 (fixed, not seat order). With ≥ 3 peekable cards the three cards are a random sample. On Easy the same assignment is drawn, then one random trader keeps its peek.
39. **Draw order.** Every random draw is made in `new_hand`, in this order: card count, face-up count, event, deal, doubled card, seat order, peeks, flip schedule. The flips are pre-drawn by simulating the hidden set, which is exact because nothing but flips changes it.
40. **"In seat order".** Takers act in absolute seat order (seat ①→④, skipping the maker and you), not cyclically from the maker. When a trader makes, you always act first.
41. **Clamp range.** A trader's est is clamped to the settle range of its own view (face-up plus its peek). That range is never wider than the public one.
42. **Empty side.** A trader that wants a side with nothing left passes, and the engine records the side it wanted, so WHAT YOU LEARNED can say "wanted your ask, it was gone". Learning updates every trader after every fill, including the aggressor and the maker; passes don't update.
43. **Rounding.** The computer bid uses the shared `make_quote`, so `round()` is half-to-even, the same as Card.
44. **Risk rule scope.** The worst case covers your whole hand position (earlier fills included) against your balance, which only changes at settle. Checking the three quote cases is sufficient: worst-case loss is convex in the bid/ask fill sizes, so no partial fill can be worse than the corners. A between-turn flip only narrows the range, so it can never push you over.
45. **No early end.** The risk rule means your balance can't go below $0, so the session always plays every hand. At $0 only riskless actions are allowed.
46. **Your take size.** It starts at 1 and moves with ←→, clamped to the side's cap (like Card's size selector). You get one action per trader market.
47. **Hiding the answer.** Before you report, the settle screen shows your trades but hides their $ and reasons, and the leaderboard shows your P&L as `??` and your rank as `?`. Because the game is zero-sum, the others' P&Ls still let you cross-check your answer. That's the "zero-sum" note.
48. **Zero-sum check.** Settling raises `AssertionError` if the four P&Ls don't sum to 0. It's an explicit check, so it still runs under `python -O`.
49. **Table fair and edge.** Table fair is recorded with every action, at the moment it happens; a flip can change it between turns. The TAKING tile shows the edge of your takes vs table fair. The history record stores that as `edge_taken`, so the shared Stats screen ("AVG EDGE TAKEN") works unchanged.
50. **Ranks.** Ranks use competition ranking, so tied P&Ls share a rank.
51. **Feed times.** The fills feed's TIME column is the replay clock (0.6 s per line). The traders act instantly in the engine.
52. **No market posted.** When your quote timer runs out, the fills screen still appears, says no market was posted, and moves on.
53. **WHAT YOU LEARNED** turns each trader's action into the range its rule implies: bought → values it ≥ ask + 1, sold → ≤ bid − 1, passed inside → between bid − 1 and ask + 1.
54. **Flip display.** On Hard the flipped card is tagged NEW, and the next turn's TABLE panel shows `▲ X turned face up`.
55. **Top bar.** Hand screens show `TRADING GAME ▸ MODE` as the spec asks. The shared lobby/custom/how-to/stats screens keep their `MTT GAMES ▸ TRADING GAME` crumb.
56. **Recap columns.** SEAT is your seat number that hand. FILLS b/a is units filled on your bid / your ask. RANK is shown as `r/4`. BANKROLL is your balance after each hand.
57. **CSV.** The CSV has one row per action on every market (plus one row for a market you never posted), with the hand's cards and settle on each row.
58. **Mistakes.** "Timeouts" covers both your quote timer (no market posted) and your take timer.
59. **Test helper reuse.** The private-fair test imports Card's enumeration helper (`brute_force`) from `tests/test_fair_value.py` instead of re-implementing it.
