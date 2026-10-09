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


## The games

Card Game: Trading against a market on hidden card values

Dice: Game: Trading against a market on hidden dice values with smaller tick sizing

Trading Game: Making a market and taking against bot markets on hidden card values


Outcry: Open market outcry across different rounds, trading a contracts hidden true value.

ETF Arb: Price a basket of stocks and race 3 traders to trade the ETF when it drifts from its NAV

## ETF Arb

`mtt-games etf [--seed N]` — the same seed gives everyone the same basket, prices, quotes, events and computer behaviour.

### Rules

- **The basket.** Each game picks N stocks (4 / 5 / 6) from AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, V, XOM, JNJ, WMT, PG, MA, HD, KO with fixed weights that sum to exactly 1 (whole tenths ≥ 0.1 on Easy, hundredths ≥ 0.05 otherwise). Starting prices are uniform in 50–600.
- **Each round** every price moves by a normal draw with sd 0.6% of price (about 1 in 5 stocks don't move), rounded to whole dollars on Easy, tenths on Medium and cents on Hard. CHG and % show the move since the last round. The **W × P** column (weight × price, rounded to the same precision as the prices) is filled in on every difficulty; the NAV row stays `Σ = ?` — adding it up is your job. **Δ W × P** shows how much each row's W × P moved since last round, and the BASKET title shows last round's NAV, so `last NAV + Σ Δ W × P` = this round's NAV exactly. CHG is each stock's own price move; summing CHG doesn't give the NAV change, because NAV moves by weight × CHG.
- **Precision by difficulty.** Prices, W × P, NAV and the ETF quote all use one tick: **whole dollars on Easy, tenths on Medium, cents on Hard**.
- **The quote.** A gap `g` is drawn: with the preset's skip-round chance `|g|` is 0.00–0.45 (a skip round), otherwise it's uniform in the preset's trade-gap range, with a 50/50 sign. `mid = NAV − g` (positive g = the ETF is cheap), `bid = round_to_tick(mid − spread/2)`, `ask = bid + spread`, where the spread is 0.20 on Medium and Hard and **$1 on Easy** (the smallest whole-dollar width). Each side has a fixed quantity (40 / 30 / 20 units) that everyone shares; trades use it up and an empty side can't be traded.
- **Your move.** One trade per round: BUY 1–20 at the ask, SELL 1–20 at the bid (capped by what's left), or SKIP. The timer (25 / 20 / 10 s) running out is a skip.
- **P&L** settles at the round's NAV: buy gross `(NAV − ask) × units`, sell gross `(bid − NAV) × units`; a flat **$10 fee** per trade; the **first trade of the round** (by anyone) earns **+20% of (gross − fee)** when that is positive. `net = gross − fee + bonus`. Example: NAV 237.50, buy 10 @ 233.40 → gross $41.00, fee −$10.00, bonus $6.20 if first → **+$37.20**.
- **The right call** (scoring): with `u = min(20, size at that side)`, BUY if `(NAV − ask) × u > 10`, SELL if `(bid − NAV) × u > 10`, else SKIP. At n units you need a gap over `$10 / n` just to cover the fee.

### NAV math

Each row's `W × P = weight × price` is rounded (half up) to the difficulty's tick — whole dollars, tenths or cents — and `NAV = Σ W × P` of those rounded values, so the column you add up gives exactly the NAV the game uses. Quotes sit on the same tick. Everything else (gross, fee, bonus, net, totals) is exact `Decimal` and only rounded to the cent for display. No floats touch money.

### Events (Hard, or on in Custom)

In about 1 round in 3 one event hits one stock. An amber banner explains it and the row is marked ⚑ (CHG reads "split" / "rebal") — but **the table does not update the weight**; you must:

| event | price shown | weight NAV uses |
|---|---|---|
| N-for-1 split (N = 2 or 3) | post-split | shown weight × N |
| 1-for-N reverse split | post-split | shown weight ÷ N |
| rebalance ("AMZN weight 0.15 → 0.20") | normal | the banner's new weight |

On an event round the ⚑ row's W × P is computed from the **stale** weight the table shows and marked amber, so fixing that cell is part of the job; the result screen shows the stale value struck through next to the correct one. The adjustment carries forward: from the next round on the table shows the adjusted weight, and NAV keeps using it.

### Computer traders

KESTREL, OSPREY and MERLIN each price the basket with a noisy NAV = true NAV + a normal error (sd $1.00 / $0.30 / $0.10). On an event round each applies the event correctly 70% of the time and otherwise uses the table's weight (it falls for the trap). Each draws a decision time per round (11–20 s / 7–14 s / 2–7 s). At its decision time it trades the side its perceived gap points to (BUY if its NAV > ask, SELL if < bid), for `min(20, units left)`, only if `gap × units > fee + $2`; an empty side or a small gap means it skips, and a decision time past the timer means it never gets in. Each trades at most once per round. The round screen shows them "pricing ▮▮▯▯▯" and then what they did.

### Presets

|                                 | EASY            | MEDIUM             | HARD               |
|---------------------------------|-----------------|--------------------|--------------------|
| stocks                          | 4               | 5                  | 6                  |
| weights / prices                | tenths / whole  | hundredths / tenths | hundredths / cents |
| quote precision · spread        | whole · $1      | tenths · 0.2        | cents · 0.20        |
| rounds · timer                  | 6 · 25s         | 6 · 20s            | 8 · 10s            |
| size at bid / ask               | 40              | 30                 | 20                 |
| skip-round chance · trade gap   | 15% · 1.20–3.50 | 22% · 0.70–3.00    | 25% · 0.55–3.00    |
| trader error sd · decision time | 1.00 · 11–20s   | 0.30 · 7–14s       | 0.10 · 2–7s        |
| events                          | off             | off                | ~1 in 3 rounds     |

Fee $10, bonus 20% and units 1–20 everywhere. Custom exposes every field (plus the traders' 70% event skill).

**Keys.** Round: B buy · S sell · K skip · ←→ units ±1 · ⇧←→ ±5 · ⏎ skip ahead (after you act) · Esc quit. Result: ⏎ next round. Recap: R replay seed · N next difficulty · E export CSV · L lobby · Q quit.

### Decisions (ETF Arb)

1. **The race depends on you.** Every computer's decision time, NAV error and event skill are drawn per round from its own seeded RNG at setup, so they never depend on your play. Whether the side is still there when it decides does: if you take 20 units first, a trader may find the side empty. A computer due on a tick acts before a keypress handled at that same tick.
2. **Clock.** 0.25 s ticks, like Outcry; decision times are rounded to ticks. The screens read `app.etf_clock` (default `time.monotonic`), which tests replace with a fake.
3. **When a round ends.** At the timer, or as soon as you and every computer whose decision time falls inside the timer have decided. After you act you can watch the rest of the race, or press ⏎ to skip to the result.
4. **Esc** on the round screen returns to the lobby (the session is abandoned: no recap or history line).
5. **Units** start at 20 (the right-call size); each button shows `min(units, left)`.
6. **Weights** are a uniform random composition on the tenths/hundredths grid above the minimum. **Moves**: 20% of stocks don't move; the rest move by `N(0, 0.6% × price)` rounded to the tick (whole dollars on Easy, tenths on Medium, cents on Hard), so some more round to zero — about 20% unchanged per round on Hard, 22% on Medium, but about 43% on Easy, where a 0.6% move on a cheap stock is often under $0.50. Round 1 shows the move from the starting prices. **Gaps** are uniform over whole cents in each band.
7. **Events.** One event per event round: kind uniform over split / reverse split / rebalance, stock uniform, N uniform over {2, 3}. A reverse split only uses an N that divides the weight exactly (÷2 always; ÷3 only when exact), so NAV stays exact. Split price = the moved price ÷ N rounded to the tick; reverse = × N. A rebalance moves the weight by ±1–2 steps (0.1 on tenths, 0.05 on hundredths), never below the minimum. After a split the weights no longer sum to 1 — they're share counts, and NAV stays continuous. The W × P column is shown on every difficulty, to cents, so the event trap lives in it: the ⚑ row's W × P uses the stale shown weight (amber) while NAV uses the adjusted one, and the result screen strikes the stale value through next to the correct one. The banner is unchanged. The traders' 70% event skill is a config field for every preset.
8. **Trader gaps** are measured against the quote (`est − ask`, `bid − est`), the same way the right call is. Errors are rounded to 4 decimals and added as `Decimal`.
9. **Scoring terms.** Right way = gross > 0. A "skip round" in the recap is a round whose *right call* is SKIP (a 0.55 gap can still be a skip once the fee is counted). RIGHT SKIPS counts skips and timeouts on those rounds. AVG DECISION averages your trades and skips, not timeouts.
10. **Mistakes.** *Right side but too small* compares with `min(20, units left when you traded)`. *Skipped a trade round* (timeouts included) shows the right call's net at max size without any bonus. *Fell for the event* means your action matched the call you'd get from the table's weights and not the true call.
11. **Shared Stats.** The history line stores your session net as `final_balance` and your total gross as `edge_taken`; there's no P&L report in this game, so report accuracy shows "—".
12. **Shell.** One new optional hook, `GameUI.lobby_note` (the lobby's footer line). The only existing test changed is the five-games list in `tests/test_outcry_app.py`. Home-screen note: "Basket Arbitrage Race". CSV export: one row per player per round.
13. **Precision follows difficulty.** Easy is whole dollars, Medium tenths, Hard cents, for prices, W × P, NAV and the ETF quote alike. Because 0.3 × 427 = 128.1, W × P is rounded per row (half up) to the tick and NAV is defined as the sum of those rounded values, so summing the visible column always gives the true NAV. A 0.20 spread can't be quoted in whole dollars, so Easy's spread is $1. With that wider spread, small gaps no longer clear the $10 fee: about 39% of Easy rounds are right-call skips, versus about 27–28% on Medium and Hard. P&L stays in dollars and cents everywhere.
14. **How often skipping is right.** Each preset sets its skip-round chance and its trade-gap range. Easy uses 15% and 1.20–3.50: with Easy's $1 spread and whole-dollar quotes, gaps under about $1.50 can't cover the $10 fee, so the range starts higher. About 16% of Easy rounds end up as right-call skips (it was about 40%). Medium uses 22% and 0.70–3.00, for about 22% skip rounds (was about 28%). Hard keeps the original 25% and 0.55–3.00, for about 27%.
15. **The NAV shortcut.** Because each row's W × P is rounded to the tick, `last NAV + Σ (weight × CHG)` only lands on the new NAV about half the time (61% Easy, 45% Medium, 43% Hard), and summing raw CHG almost never does. So the basket has a **Δ W × P** column (the change in each row's rounded W × P) and the title shows last round's NAV (or the opening NAV before round 1); `last NAV + Σ Δ W × P` is exact every round. On a ⚑ event round that row's Δ uses the stale weight, like its W × P, so the shortcut reproduces the trap. The result screen strikes the stale Δ through next to the adjusted one.
